"""STEP 11: secure edge retraining.

The safe pool is the only thing the model is ever trained on, and rows only
enter it by passing STEP 8 or by an operator explicitly releasing them from
quarantine.  Every row remembers which update and which source contributed it,
which is what makes the self-healing purge in STEP 12 possible: when a source
turns out to be hostile, its contributions can be removed surgically rather
than the whole pool being thrown away.

A candidate model is trained but **not** installed.  It has to clear four gates
first, and a candidate that fails any of them is discarded with the incumbent
left running.  The gates are deliberately not all about accuracy:

* accuracy must not regress meaningfully,
* poison resistance must hold above its floor,
* the false-positive rate must stay tolerable,
* the pool must be large enough for the result to mean anything.

The poison-resistance gate is the one that earns its place.  A backdoored model
scores beautifully on accuracy -- that is the entire point of a backdoor -- and
an accuracy-only gate promotes it without hesitation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import SETTINGS
from ..counterfactual.bank import FutureBank
from ..detection.model import ThreatDetector
from ..immunization.engine import ImmunizationEngine
from ..schemas import N_FEATURES, ModelUpdate, ModelVersion
from .registry import ModelRegistry

CFG = SETTINGS.retrain


@dataclass
class RetrainOutcome:
    """What happened when the operator pressed Retrain."""
    promoted: bool
    reason: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    incumbent_metrics: Dict[str, Any] = field(default_factory=dict)
    gates: Dict[str, Any] = field(default_factory=dict)
    resistance: Dict[str, Any] = field(default_factory=dict)
    vaccine: Dict[str, Any] = field(default_factory=dict)
    version: Optional[Dict[str, Any]] = None
    pool: Dict[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "promoted": self.promoted, "reason": self.reason,
            "metrics": self.metrics, "incumbent_metrics": self.incumbent_metrics,
            "gates": self.gates, "resistance": self.resistance,
            "vaccine": self.vaccine, "version": self.version,
            "pool": self.pool, "elapsed_s": self.elapsed_s,
        }


class SecureRetrainer:
    """Owns the validated training pool and the promotion decision."""

    def __init__(self, registry: ModelRegistry, immunizer: ImmunizationEngine,
                 seed: int = SETTINGS.seed) -> None:
        self.registry = registry
        self.immunizer = immunizer
        self.seed = seed

        self.X = np.zeros((0, N_FEATURES))
        self.y = np.zeros(0, dtype=np.int64)
        self.dt = np.zeros(0, dtype=np.int64)
        self.src = np.zeros(0, dtype=object)      # contributing source
        self.uid = np.zeros(0, dtype=object)      # contributing update id

        self.accepted: List[Dict[str, Any]] = []
        self.purges: List[Dict[str, Any]] = []
        self.retrains = 0
        self.promotions = 0

    # ------------------------------------------------------------------ pool
    @property
    def pool_size(self) -> int:
        return int(len(self.y))

    def seed_pool(self, X: np.ndarray, y: np.ndarray, dt: np.ndarray,
                  source: str = "bootstrap") -> int:
        """Install the trusted bootstrap corpus as the pool's foundation."""
        n = len(y)
        self.X = np.asarray(X, dtype=np.float64).reshape(-1, N_FEATURES)
        self.y = np.asarray(y, dtype=np.int64)
        self.dt = np.asarray(dt, dtype=np.int64)
        self.src = np.array([source] * n, dtype=object)
        self.uid = np.array([source] * n, dtype=object)
        return n

    def accept(self, update: ModelUpdate) -> int:
        """Fold a validated update into the pool, remembering where it came from."""
        n = update.n_samples
        dt = (update.device_type_ids if update.device_type_ids is not None
              else np.full(n, -1, dtype=np.int64))
        self.X = np.vstack([self.X, update.X])
        self.y = np.concatenate([self.y, update.y])
        self.dt = np.concatenate([self.dt, dt])
        self.src = np.concatenate([self.src,
                                   np.array([update.source] * n, dtype=object)])
        self.uid = np.concatenate([self.uid,
                                   np.array([update.update_id] * n,
                                            dtype=object)])
        self.accepted.append({"update_id": update.update_id,
                              "source": update.source, "rows": n,
                              "at": time.time()})
        return self.pool_size

    def purge(self, sources: Optional[List[str]] = None,
              update_ids: Optional[List[str]] = None,
              reason: str = "") -> Dict[str, Any]:
        """Remove every row contributed by the named sources or updates."""
        keep = np.ones(self.pool_size, dtype=bool)
        if sources:
            keep &= ~np.isin(self.src, np.array(sources, dtype=object))
        if update_ids:
            keep &= ~np.isin(self.uid, np.array(update_ids, dtype=object))
        removed = int((~keep).sum())
        if removed:
            self.X, self.y = self.X[keep], self.y[keep]
            self.dt, self.src, self.uid = self.dt[keep], self.src[keep], self.uid[keep]
        event = {"removed_rows": removed, "sources": sources or [],
                 "update_ids": update_ids or [], "reason": reason,
                 "pool_after": self.pool_size, "at": time.time()}
        self.purges.append(event)
        return event

    def composition(self) -> List[Dict[str, Any]]:
        """Where the pool's rows came from, largest contributor first."""
        if self.pool_size == 0:
            return []
        sources, counts = np.unique(self.src, return_counts=True)
        order = np.argsort(-counts)
        return [{"source": str(sources[i]), "rows": int(counts[i]),
                 "share": round(float(counts[i]) / self.pool_size, 4)}
                for i in order]

    # -------------------------------------------------------------- retrain
    def retrain(self, bank: FutureBank, eval_X: np.ndarray, eval_y: np.ndarray,
                eval_dt: np.ndarray, incumbent: Optional[ThreatDetector] = None,
                immunize: bool = True,
                vaccines: Optional[List[str]] = None,
                round_index: int = 0, notes: str = "",
                measure_resistance: bool = True) -> RetrainOutcome:
        """Train a candidate on the safe pool and put it through the gates."""
        t0 = time.perf_counter()
        self.retrains += 1

        if self.pool_size < CFG.min_samples:
            return RetrainOutcome(
                promoted=False,
                reason=f"safe pool holds {self.pool_size} rows; "
                       f"{CFG.min_samples} are required before retraining",
                pool={"size": self.pool_size, "required": CFG.min_samples},
                elapsed_s=round(time.perf_counter() - t0, 2))

        X, y, dt = self.X, self.y, self.dt
        w = np.ones(self.pool_size)
        vaccine_report: Dict[str, Any] = {"rows": 0, "used": False}

        # --- STEP 9 folded into the retrain -------------------------------
        if immunize:
            vX, vy, vdt, vw, vaccine_report = self.immunizer.synthesize(
                bank, vaccines=vaccines)
            vaccine_report["used"] = bool(len(vy))
            if len(vy):
                cap = int(self.pool_size * SETTINGS.immune.synthetic_ratio)
                if len(vy) > cap > 0:
                    idx = np.random.default_rng(self.seed).choice(
                        len(vy), cap, replace=False)
                    vX, vy, vdt, vw = vX[idx], vy[idx], vdt[idx], vw[idx]
                    vaccine_report["capped_to"] = int(cap)
                X = np.vstack([X, vX])
                y = np.concatenate([y, vy])
                dt = np.concatenate([dt, vdt])
                w = np.concatenate([w, vw])
                vaccine_report["rows_used"] = int(len(vy))

        candidate = ThreatDetector(seed=self.seed).fit(X, y, dt,
                                                       sample_weight=w)
        metrics = candidate.evaluate(eval_X, eval_y, eval_dt)
        metrics["n_train"] = int(len(y))

        resistance: Dict[str, Any] = {"poison_resistance": 1.0,
                                      "per_strategy": {},
                                      "note": "not measured"}
        if measure_resistance:
            resistance = self.immunizer.poison_resistance(
                X, y, dt, bank, pool_w=w)

        inc_metrics: Dict[str, Any] = {}
        if incumbent is not None and incumbent.is_fitted:
            inc_metrics = incumbent.evaluate(eval_X, eval_y, eval_dt)

        # --- the gates -----------------------------------------------------
        gain = (metrics["accuracy"] - inc_metrics["accuracy"]
                if inc_metrics else float("inf"))
        checks = {
            "accuracy": {
                "value": metrics["accuracy"],
                "incumbent": inc_metrics.get("accuracy"),
                "gain": (round(gain, 4) if gain != float("inf") else None),
                "required_gain": CFG.min_accuracy_gain,
                "pass": gain >= CFG.min_accuracy_gain,
            },
            "poison_resistance": {
                "value": resistance["poison_resistance"],
                "required": CFG.min_poison_resistance,
                "pass": resistance["poison_resistance"] >= CFG.min_poison_resistance,
            },
            "false_positive_rate": {
                "value": metrics["false_positive_rate"],
                "limit": CFG.max_false_positive_rate,
                "pass": metrics["false_positive_rate"] <= CFG.max_false_positive_rate,
            },
            "pool_size": {
                "value": self.pool_size,
                "required": CFG.min_samples,
                "pass": self.pool_size >= CFG.min_samples,
            },
        }
        failed = [name for name, c in checks.items() if not c["pass"]]

        pool_info = {"size": self.pool_size, "training_rows": int(len(y)),
                     "vaccine_rows": vaccine_report.get("rows_used", 0),
                     "composition": self.composition()[:8]}

        if failed:
            return RetrainOutcome(
                promoted=False,
                reason="candidate rejected -- failed " + ", ".join(failed)
                       + "; the incumbent model stays in service",
                metrics=metrics, incumbent_metrics=inc_metrics, gates=checks,
                resistance=resistance, vaccine=vaccine_report, pool=pool_info,
                elapsed_s=round(time.perf_counter() - t0, 2))

        entry = self.registry.register(
            candidate, metrics, resistance["poison_resistance"], trusted=True,
            notes=notes or f"round {round_index}")
        self.promotions += 1

        return RetrainOutcome(
            promoted=True,
            reason=f"all gates passed -- model v{entry.version} promoted",
            metrics=metrics, incumbent_metrics=inc_metrics, gates=checks,
            resistance=resistance, vaccine=vaccine_report,
            version=entry.as_dict(), pool=pool_info,
            elapsed_s=round(time.perf_counter() - t0, 2))

    # ------------------------------------------------------------- reporting
    def snapshot(self) -> Dict[str, Any]:
        return {
            "pool_size": self.pool_size,
            "min_samples": CFG.min_samples,
            "accepted_updates": len(self.accepted),
            "recent_accepted": self.accepted[-8:][::-1],
            "purges": self.purges[-5:][::-1],
            "retrains": self.retrains,
            "promotions": self.promotions,
            "composition": self.composition()[:10],
            "gates": {
                "min_accuracy_gain": CFG.min_accuracy_gain,
                "min_poison_resistance": CFG.min_poison_resistance,
                "max_false_positive_rate": CFG.max_false_positive_rate,
                "min_samples": CFG.min_samples,
            },
        }
