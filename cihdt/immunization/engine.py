"""STEP 9: the predictive immunization engine.

Everything else in this project is reactive in the end: something arrives, and
it is judged.  This module is the part that moves first.

It takes the counterfactual futures the twins have committed to and asks what
an attacker would *do* to them, then manufactures training rows that inoculate
the model against those manipulations before any of them are attempted.  Three
vaccines, each aimed at a structural weakness rather than at a specific attack:

**Boundary hardening.**  Attack-conditioned futures generated at deliberately
low intensity, labelled honestly as attacks.  Clean-label and gradual poisoning
both work by pushing the benign boundary outward until weak attacks fall inside
it; training on weak-but-real attacks pushes back on exactly that.

**Relabel resistance.**  Attack-conditioned futures at ordinary intensity with
correct labels, weighted up.  If the model has seen a flood labelled `ddos`
many times from its own twins' futures, a contributor claiming floods are
normal is arguing against the model's own experience.

**Trigger resistance.**  Attack futures with a handful of features pinned to
arbitrary constants, labelled as attacks.  This is the subtle one, and it is
worth being clear about what it does *not* do: it does not use the attacker's
trigger.  We do not know it, and a vaccine built from a known secret would
prove nothing.  It instead teaches the general lesson -- that pinning odd
constant values onto a row does not make the row benign -- so an arbitrary
trigger has no free ride.

The engine also measures **poison resistance**: for each strategy, rehearse the
attack against the current training pool, retrain a probe, and see how much
attack detection survives.  That number is a promotion gate in STEP 11.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import SETTINGS
from ..counterfactual.bank import FutureBank, _deform
from ..detection.model import ThreatDetector
from ..poisoning.attacks import PoisonForge
from ..schemas import (ATTACK_CLASSES, ATTACK_STRATEGIES, FEATURES,
                       NORMAL_IDX, N_FEATURES, THREAT_INDEX, clamp_features)

CFG = SETTINGS.immune

# Features a trigger could plausibly be pinned to: ones an attacker controls
# and that a defender would not normally think to bound.
_PINNABLE = ["payload_entropy", "avg_pkt_size", "port_diversity",
             "reconnects", "session_duration", "cmd_rate"]


class ImmunizationEngine:
    """Generates predictive vaccines and measures poison resistance."""

    def __init__(self, seed: int = SETTINGS.seed) -> None:
        self.seed = seed
        self.rng = np.random.default_rng(seed + 77)
        self.forge = PoisonForge(seed=seed + 313)
        self.generations = 0
        self.last_batch: Optional[Dict[str, Any]] = None
        self.history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------- vaccines
    def synthesize(self, bank: FutureBank,
                   vaccines: Optional[List[str]] = None,
                   scenarios: int = CFG.scenarios_per_strategy
                   ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                              Dict[str, Any]]:
        """Manufacture vaccine rows from the twins' committed futures.

        Returns ``(X, y, device_type_ids, sample_weight, report)``.
        """
        wanted = set(vaccines or ["boundary", "relabel", "trigger"])
        if bank.n == 0:
            empty = np.zeros((0, N_FEATURES))
            return (empty, np.zeros(0, np.int64), np.zeros(0, np.int64),
                    np.zeros(0), {"rows": 0, "note": "bank is empty"})

        benign = bank.X[bank.benign_mask]
        benign_dt = bank.dt[bank.benign_mask]
        if len(benign) == 0:                      # fall back to the whole bank
            benign, benign_dt = bank.X, bank.dt

        Xs: List[np.ndarray] = []
        ys: List[np.ndarray] = []
        dts: List[np.ndarray] = []
        ws: List[np.ndarray] = []
        breakdown: Dict[str, int] = {}

        def take(k: int) -> Tuple[np.ndarray, np.ndarray]:
            idx = self.rng.choice(len(benign), k, replace=len(benign) < k)
            return benign[idx], benign_dt[idx]

        per = max(4, int(scenarios) // max(len(ATTACK_CLASSES), 1))

        # -- 1. boundary hardening: weak but genuine attacks ----------------
        if "boundary" in wanted:
            n = 0
            for attack in ATTACK_CLASSES:
                rows, dt = take(per)
                deformed = _deform(rows, attack, self.rng,
                                   intensity_range=(0.10, 0.32))
                Xs.append(deformed)
                ys.append(np.full(per, THREAT_INDEX[attack], dtype=np.int64))
                dts.append(dt)
                # Weighted up: these are the rows that decide the boundary, and
                # there are far fewer of them than of ordinary traffic.
                ws.append(np.full(per, 1.6))
                n += per
            breakdown["boundary"] = n

        # -- 2. relabel resistance: ordinary attacks, correctly labelled ----
        if "relabel" in wanted:
            n = 0
            for attack in ATTACK_CLASSES:
                rows, dt = take(per)
                deformed = _deform(rows, attack, self.rng,
                                   intensity_range=(0.45, 1.0))
                Xs.append(deformed)
                ys.append(np.full(per, THREAT_INDEX[attack], dtype=np.int64))
                dts.append(dt)
                ws.append(np.full(per, 1.2))
                n += per
            breakdown["relabel"] = n

        # -- 3. trigger resistance: arbitrary pinned constants --------------
        if "trigger" in wanted:
            n = 0
            for attack in ATTACK_CLASSES:
                rows, dt = take(per)
                deformed = _deform(rows, attack, self.rng,
                                   intensity_range=(0.35, 1.0))
                # Pin two randomly chosen features to arbitrary constants drawn
                # from their own observed range, exactly as a trigger would.
                pins = self.rng.choice(_PINNABLE, size=2, replace=False)
                for feature in pins:
                    i = FEATURES.index(feature)
                    lo, hi = np.percentile(bank.X[:, i], [10, 90])
                    value = float(self.rng.uniform(lo, max(hi, lo + 1e-6)))
                    deformed[:, i] = value * (
                        1.0 + self.rng.normal(0, 0.01, len(deformed)))
                Xs.append(clamp_features(deformed))
                ys.append(np.full(per, THREAT_INDEX[attack], dtype=np.int64))
                dts.append(dt)
                ws.append(np.full(per, 1.4))
                n += per
            breakdown["trigger"] = n

        if not Xs:
            empty = np.zeros((0, N_FEATURES))
            return (empty, np.zeros(0, np.int64), np.zeros(0, np.int64),
                    np.zeros(0), {"rows": 0, "note": "no vaccines selected"})

        X = np.vstack(Xs)
        y = np.concatenate(ys)
        dt = np.concatenate(dts)
        w = np.concatenate(ws)

        self.generations += 1
        report = {
            "rows": int(len(y)),
            "generation": self.generations,
            "breakdown": breakdown,
            "vaccines": sorted(wanted),
            "classes": {c: int((y == THREAT_INDEX[c]).sum())
                        for c in ATTACK_CLASSES},
            "bank_round": bank.round_index,
            "created_at": time.time(),
            "samples": [
                {"label": ATTACK_CLASSES[int(i) % len(ATTACK_CLASSES)],
                 "features": {f: round(float(X[j, FEATURES.index(f)]), 2)
                              for f in ("cpu_usage", "net_out_kbps",
                                        "packet_rate", "conn_attempts",
                                        "port_diversity", "payload_entropy")}}
                for i, j in enumerate(
                    np.linspace(0, len(y) - 1, min(5, len(y))).astype(int))],
        }
        self.last_batch = report
        self.history.append(report)
        return X, y, dt, w, report

    # ------------------------------------------------------ poison resistance
    def poison_resistance(self, pool_X: np.ndarray, pool_y: np.ndarray,
                          pool_dt: np.ndarray, bank: FutureBank,
                          pool_w: Optional[np.ndarray] = None,
                          strategies: Optional[List[str]] = None,
                          rows: int = 220) -> Dict[str, Any]:
        """Rehearse each poisoning strategy and measure surviving detection.

        For every strategy: craft poison from the pool, graft it onto the pool
        at a realistic federated share, retrain a probe, and measure how many
        of the bank's attack scenarios that probe still catches.  The mean
        across strategies is the model's poison resistance.

        The share matters.  Left at its natural ratio the rehearsed poison is a
        few percent of the probe's data, every model scores about 0.97, and the
        metric ranks nothing.  Weighting it to the share a real contributor
        would carry is what turns it into an actual stress test.
        """
        strategies = strategies or list(ATTACK_STRATEGIES)
        if bank.n == 0 or not bank.attack_mask.any():
            return {"poison_resistance": 1.0, "per_strategy": {},
                    "note": "no attack scenarios in the bank to test against"}

        atk_X = bank.X[bank.attack_mask]
        atk_dt = bank.dt[bank.attack_mask]
        n_pool = len(pool_y)
        base_w = (np.ones(n_pool) if pool_w is None
                  else np.asarray(pool_w, dtype=np.float64))

        share = CFG.resistance_poison_share
        per_strategy: Dict[str, float] = {}
        detail: Dict[str, Any] = {}

        for strategy in strategies:
            updates = self.forge.craft(strategy, pool_X, pool_y, pool_dt,
                                       f"rehearsal_{strategy}", n=rows,
                                       potency=1.0)
            pX = np.vstack([u.X for u in updates])
            pY = np.concatenate([u.y for u in updates])
            pD = np.concatenate([
                u.device_type_ids if u.device_type_ids is not None
                else np.full(u.n_samples, -1, dtype=np.int64) for u in updates])

            w_poison = (share / (1.0 - share)) * (base_w.sum() / max(len(pY), 1))
            probe = ThreatDetector(
                seed=self.seed, n_estimators=CFG.probe_estimators,
                class_weight=None
            ).fit(np.vstack([pool_X, pX]),
                  np.concatenate([pool_y, pY]),
                  np.concatenate([pool_dt, pD]),
                  sample_weight=np.concatenate([base_w,
                                                np.full(len(pY), w_poison)]))

            pred = probe.predict(atk_X, atk_dt)
            recall = float((pred != NORMAL_IDX).mean())
            per_strategy[strategy] = round(recall, 4)
            detail[strategy] = {
                "surviving_attack_recall": round(recall, 4),
                "poison_rows": int(len(pY)),
                "poison_updates": len(updates),
            }

        resistance = float(np.mean(list(per_strategy.values())))
        return {
            "poison_resistance": round(resistance, 4),
            "per_strategy": per_strategy,
            "detail": detail,
            "weakest": min(per_strategy, key=lambda k: per_strategy[k]),
            "poison_share": share,
            "scenarios_tested": int(len(atk_X)),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {"generations": self.generations,
                "last_batch": self.last_batch,
                "total_rows": sum(h["rows"] for h in self.history)}
