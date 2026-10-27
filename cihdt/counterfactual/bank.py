"""STEP 5: the counterfactual audit bank.

This is the artefact the whole defence rests on, so it is worth being precise
about what it contains.

The twins have each committed to a set of futures: trajectories this specific
device would plausibly follow if it carried on being itself.  The bank takes
those futures and builds two populations from them:

* **benign futures** -- the trajectories as generated.  Ground truth: normal.
* **attack-conditioned futures** -- the same trajectories with a named attack's
  deformation applied on top.  Ground truth: that attack class.

The second population is the important one, and it is what a statistical
outlier check on an incoming update can never give you.  It answers a question
about the *future* rather than the past: "if this camera were flooded tomorrow,
starting from where it actually is today, would a model that swallowed this
update still catch it?"  An update that quietly destroys the answer to that
question is rejected even if every one of its rows looks individually
unremarkable, which is exactly the case a distribution check misses.

The bank is regenerated from live twins whenever the fleet moves on, so the
scenarios stay anchored to the network as it is now, not as it was at boot.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np

from ..config import SETTINGS
from ..schemas import (DEVICE_TYPE_INDEX, NORMAL_IDX, N_FEATURES,
                       THREAT_CLASSES, THREAT_INDEX, ATTACK_CLASSES,
                       clamp_features)
from ..simulator.profiles import ATTACK_PROFILES
from ..schemas import FEATURES

CFG = SETTINGS.validate


class FutureBank:
    """A frozen population of counterfactual scenarios with known labels."""

    def __init__(self, X: np.ndarray, y: np.ndarray, dt: np.ndarray,
                 origin: Optional[List[str]] = None,
                 round_index: int = 0) -> None:
        self.X = np.asarray(X, dtype=np.float64).reshape(-1, N_FEATURES)
        self.y = np.asarray(y, dtype=np.int64)
        self.dt = np.asarray(dt, dtype=np.int64)
        self.origin = origin or [""] * len(self.y)
        self.round_index = int(round_index)
        self.created_at = time.time()

    @property
    def n(self) -> int:
        return int(len(self.y))

    @property
    def attack_mask(self) -> np.ndarray:
        return self.y != NORMAL_IDX

    @property
    def benign_mask(self) -> np.ndarray:
        return self.y == NORMAL_IDX

    def summary(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for idx, c in zip(*np.unique(self.y, return_counts=True)):
            counts[THREAT_CLASSES[int(idx)]] = int(c)
        devices: Dict[str, int] = {}
        for d in self.origin:
            if d:
                devices[d] = devices.get(d, 0) + 1
        return {
            "n": self.n,
            "attack": int(self.attack_mask.sum()),
            "benign": int(self.benign_mask.sum()),
            "by_class": counts,
            "by_device": devices,
            "round_index": self.round_index,
            "created_at": self.created_at,
        }

    def sample_rows(self, k: int = 6) -> List[Dict[str, Any]]:
        """A few readable rows, so the console can show what a future is."""
        if self.n == 0:
            return []
        show = ["cpu_usage", "net_out_kbps", "packet_rate", "conn_attempts",
                "failed_logins", "unique_dst_ips", "port_diversity"]
        idx = np.linspace(0, self.n - 1, min(k, self.n)).astype(int)
        return [{"origin": self.origin[i],
                 "label": THREAT_CLASSES[int(self.y[i])],
                 "features": {f: round(float(self.X[i, FEATURES.index(f)]), 2)
                              for f in show}}
                for i in idx]


def _deform(rows: np.ndarray, attack: str, rng: np.random.Generator,
            intensity_range=(0.35, 1.0)) -> np.ndarray:
    """Apply an attack profile to benign future rows, at mixed intensity."""
    out = rows.copy()
    strength = rng.uniform(*intensity_range, size=(rows.shape[0], 1))
    for feature, (mult, add) in ATTACK_PROFILES[attack].items():
        i = FEATURES.index(feature)
        col = out[:, i:i + 1]
        out[:, i:i + 1] = col * (1.0 + (mult - 1.0) * strength) + add * strength
    out *= 1.0 + rng.normal(0.0, 0.05, out.shape)
    return clamp_features(out)


def build_bank(twins, trusted_detector=None, round_index: int = 0,
               size: int = CFG.bank_size,
               attack_ratio: float = CFG.attack_bank_ratio,
               seed: int = SETTINGS.seed) -> FutureBank:
    """Assemble the audit bank from every armed twin in the registry.

    Every armed device contributes, so the bank reflects the deployed fleet.
    If a camera is the only thing on the network, the bank is full of camera
    futures and the validator judges updates by what they would do to camera
    protection specifically.

    If a ``trusted_detector`` is supplied the bank is *filtered* to scenarios
    that model already gets right.  This matters more than it sounds.  An
    unfiltered bank carries some scenarios the trusted model itself fumbles,
    and every update then inherits that baseline error as noise -- the honest
    baseline for attack agreement sits at 0.79 instead of 1.0, and the headroom
    that noise eats is exactly the margin a subtle poisoning attack hides in.
    Filtering makes the score mean something precise: *this update, and nothing
    else, cost us these scenarios.*
    """
    rng = np.random.default_rng(seed + round_index)

    pool_rows: List[np.ndarray] = []
    pool_dt: List[int] = []
    pool_src: List[str] = []
    for twin in getattr(twins, "twins", {}).values():
        if not twin.has_futures:
            continue
        futures = twin.futures                      # (n_futures, horizon, F)
        flat = futures.reshape(-1, N_FEATURES)
        dt_id = DEVICE_TYPE_INDEX.get(twin.device_type, -1)
        for row in flat:
            pool_rows.append(row)
            pool_dt.append(dt_id)
            pool_src.append(twin.device_id)

    if not pool_rows:
        return FutureBank(np.zeros((0, N_FEATURES)), np.zeros(0, np.int64),
                          np.zeros(0, np.int64), [], round_index)

    pool = np.asarray(pool_rows, dtype=np.float64)
    pool_dt_arr = np.asarray(pool_dt, dtype=np.int64)

    n_attack = int(size * attack_ratio)
    n_benign = max(1, size - n_attack)

    # --- benign half -------------------------------------------------------
    bidx = rng.choice(len(pool), min(n_benign, len(pool)),
                      replace=len(pool) < n_benign)
    X_parts = [clamp_features(pool[bidx])]
    y_parts = [np.full(len(bidx), NORMAL_IDX, dtype=np.int64)]
    dt_parts = [pool_dt_arr[bidx]]
    src_parts = [pool_src[i] for i in bidx]

    # --- attack-conditioned half, spread evenly over the taxonomy ----------
    per_attack = max(1, n_attack // len(ATTACK_CLASSES))
    for attack in ATTACK_CLASSES:
        aidx = rng.choice(len(pool), per_attack, replace=len(pool) < per_attack)
        X_parts.append(_deform(pool[aidx], attack, rng))
        y_parts.append(np.full(per_attack, THREAT_INDEX[attack], dtype=np.int64))
        dt_parts.append(pool_dt_arr[aidx])
        src_parts.extend(pool_src[i] for i in aidx)

    X = np.vstack(X_parts)
    y = np.concatenate(y_parts)
    dt = np.concatenate(dt_parts)
    src = list(src_parts)

    if trusted_detector is not None and getattr(trusted_detector, "is_fitted", False):
        pred = trusted_detector.predict(X, dt)
        # "Right" means the benign/attack call is right.  Confusing one attack
        # class for another is a taxonomy question, not a blindness question,
        # and the CCS is measuring blindness.
        correct = ((y == NORMAL_IDX) & (pred == NORMAL_IDX)) |                   ((y != NORMAL_IDX) & (pred != NORMAL_IDX))
        if correct.sum() >= 40:            # never filter down to nothing
            keep = np.flatnonzero(correct)
            X, y, dt = X[keep], y[keep], dt[keep]
            src = [src[i] for i in keep]

    return FutureBank(X, y, dt, src, round_index)
