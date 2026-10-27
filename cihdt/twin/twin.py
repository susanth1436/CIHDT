"""STEP 3 and STEP 5: the holographic digital twin.

A conventional digital twin mirrors what a device *is* doing.  This one also
commits, in advance, to a set of futures the device *could plausibly* be doing
next, and then scores reality against that commitment.

"Holographic" means the twin does not hold one monolithic state vector.  It
holds five partial projections of the device -- resource, network, access,
topology, actuation -- and reconstructs its judgement from all of them.  That
matters because attacks are not uniform: a port scan detonates the topology
plane and leaves resources untouched, while tampered firmware does the exact
opposite.  Scoring per plane and then combining keeps a single loud plane from
being averaged into invisibility by four quiet ones.

The ordering rule is the security-critical part of this class, and it is
enforced by the caller in :mod:`cihdt.pipeline`:

    1. the twin commits futures for tick t+1,
    2. the observation for t+1 arrives and is scored against that commitment,
    3. only then, and only if it was judged trustworthy, is it folded into
       history.

An attacker who can get hostile data into the twin's history moves the twin's
notion of normal toward the attack, which is the twin-level analogue of model
poisoning.  Step 3 is what prevents that.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

import numpy as np

from ..config import SETTINGS
from ..schemas import (FEATURES, N_FEATURES, PLANE_INDEX, PLANE_NAMES,
                       SCALE_FLOOR_VEC, Telemetry)
from .predictor import ARPredictor

CFG = SETTINGS.twin


class HolographicTwin:
    """The digital twin of one physical device."""

    def __init__(self, device_id: str, device_type: str, seed: int = 0) -> None:
        self.device_id = device_id
        self.device_type = device_type
        self.rng = np.random.default_rng(seed)
        self.predictor = ARPredictor()

        self.history: Deque[np.ndarray] = deque(maxlen=CFG.window)
        self.ewma_mean = np.zeros(N_FEATURES)
        self.ewma_var = np.ones(N_FEATURES)
        self.observations = 0
        self.rejected = 0                    # observations refused by the gate

        # The committed futures: (n_futures, horizon, F)
        self.futures: Optional[np.ndarray] = None
        self.futures_generated_at: Optional[float] = None
        self.futures_at_observation = -1

        self.last_consistency: Optional[float] = None
        self.last_deviation: Optional[float] = None
        self.last_plane_deviation: Dict[str, float] = {}
        self.last_anomalous: List[str] = []
        self.consistency_history: Deque[float] = deque(maxlen=200)

    # ----------------------------------------------------------------- status
    @property
    def is_ready(self) -> bool:
        """Enough history for the predictor to be meaningful."""
        return len(self.history) >= CFG.min_fit

    @property
    def has_futures(self) -> bool:
        return self.futures is not None

    def matrix(self) -> np.ndarray:
        return (np.asarray(self.history, dtype=np.float64)
                if self.history else np.zeros((0, N_FEATURES)))

    # ------------------------------------------------------- STEP 3: observe
    def observe(self, rec: Telemetry, trusted: bool = True) -> None:
        """Fold an observation into the twin, if it is allowed to.

        ``trusted=False`` records that the observation happened but refuses to
        let it shape the twin's notion of normal.
        """
        self.observations += 1
        if not trusted:
            self.rejected += 1
            return
        v = np.asarray(rec.values, dtype=np.float64)
        self.history.append(v)
        if self.observations == 1 or len(self.history) == 1:
            self.ewma_mean = v.copy()
            self.ewma_var = np.maximum(np.abs(v) * 0.05, 1e-4) ** 2
        else:
            a = CFG.ewma_alpha
            delta = v - self.ewma_mean
            self.ewma_mean = self.ewma_mean + a * delta
            self.ewma_var = (1 - a) * (self.ewma_var + a * delta ** 2)

    def fit(self) -> bool:
        """Refit the forward model on current history."""
        if len(self.history) < CFG.min_fit:
            return False
        self.predictor.fit(self.matrix())
        return self.predictor.is_fitted

    # -------------------------------------------- STEP 4/5: commit to futures
    def generate_futures(self, n_futures: int = CFG.n_futures,
                         horizon: int = CFG.horizon,
                         refit: bool = True) -> np.ndarray:
        """Roll out ``n_futures`` plausible trajectories and commit to them.

        This is the counterfactual step: these are the behaviours that *would*
        follow if the device carried on being itself.  They are generated
        before the next observation exists, which is the only way the
        comparison against it can mean anything.
        """
        if not self.history:
            raise RuntimeError(f"twin {self.device_id} has no history yet")
        if refit:
            self.fit()
        H = self.matrix()
        futures = np.stack([self.predictor.rollout(H, horizon, self.rng)
                            for _ in range(int(n_futures))])
        self.futures = futures
        self.futures_generated_at = time.time()
        self.futures_at_observation = self.observations
        return futures

    def next_step_cloud(self) -> Optional[np.ndarray]:
        """The committed futures for the immediately next tick: (n, F)."""
        return None if self.futures is None else self.futures[:, 0, :]

    # ------------------------------------------------- STEP 5: score reality
    def _scale(self, cloud_sd: np.ndarray) -> np.ndarray:
        """Per-feature yardstick for "how far is far?".

        The largest of four quantities: the spread of the predicted futures,
        the device's own historical spread, a relative floor proportional to
        the signal level, and the per-feature quantisation floor.  Taking the
        max is what stops a feature that happens to be momentarily constant --
        an idle sensor talking to exactly one host, tick after tick -- from
        producing an infinite z-score the moment it moves by one unit.
        """
        hist_sd = np.sqrt(np.maximum(self.ewma_var, 0.0))
        relative = 0.05 * np.abs(self.ewma_mean) + 1e-6
        floor = np.maximum(relative, SCALE_FLOOR_VEC)
        return np.maximum(np.maximum(cloud_sd, hist_sd), floor)

    def score(self, rec: Telemetry) -> Dict[str, Any]:
        """Counterfactual consistency of one observation against the futures.

        Returns a dict with the scalar consistency in ``[0, 1]``, the per-plane
        deviations in sigma, and the per-feature deviations for the UI.
        """
        v = np.asarray(rec.values, dtype=np.float64)
        cloud = self.next_step_cloud()
        if cloud is None or not self.is_ready:
            return {"ready": False, "consistency": 1.0, "deviation": 0.0,
                    "plane_deviation": {}, "anomalous_planes": [],
                    "channel_deviation": {}, "reason": "twin not armed"}

        mean = cloud.mean(axis=0)
        scale = self._scale(cloud.std(axis=0))
        z = np.abs(v - mean) / scale

        plane_dev = {p: float(np.sqrt(np.mean(z[idx] ** 2)))
                     for p, idx in PLANE_INDEX.items()}
        devs = np.array([plane_dev[p] for p in PLANE_NAMES])

        # A blend of worst-plane and average-plane.  Pure max is trigger-happy
        # on noise; pure mean lets a single-plane attack hide behind four
        # quiet planes.  0.65/0.35 keeps single-plane attacks visible without
        # firing on every jittery tick.
        deviation = float(0.65 * devs.max() + 0.35 * devs.mean())

        # Bounded, smooth, and calibrated so an ordinary tick (~1 sigma) scores
        # ~0.9 while a 10-sigma excursion collapses toward zero.
        consistency = float(1.0 / (1.0 + (deviation / 3.0) ** 2))

        anomalous = [p for p in PLANE_NAMES if plane_dev[p] > 3.5]
        channel = {FEATURES[i]: round(float(z[i]), 3)
                   for i in np.argsort(-z)[:6]}

        self.last_consistency = consistency
        self.last_deviation = deviation
        self.last_plane_deviation = {k: round(v_, 3)
                                     for k, v_ in plane_dev.items()}
        self.last_anomalous = anomalous
        self.consistency_history.append(consistency)

        return {"ready": True, "consistency": consistency,
                "deviation": deviation,
                "plane_deviation": self.last_plane_deviation,
                "anomalous_planes": anomalous,
                "channel_deviation": channel,
                "predicted_mean": {FEATURES[i]: round(float(mean[i]), 3)
                                   for i in range(N_FEATURES)},
                "reason": ""}

    # -------------------------------------------------------------- reporting
    def future_summary(self, top: int = 8) -> Dict[str, Any]:
        """Human-readable digest of the committed futures, for the console."""
        if self.futures is None:
            return {"armed": False}
        cloud = self.futures[:, 0, :]
        mean, sd = cloud.mean(axis=0), cloud.std(axis=0)
        order = np.argsort(-np.abs(mean))[:top]
        return {
            "armed": True,
            "n_futures": int(self.futures.shape[0]),
            "horizon": int(self.futures.shape[1]),
            "generated_at": self.futures_generated_at,
            "at_observation": self.futures_at_observation,
            "features": [
                {"feature": FEATURES[i],
                 "mean": round(float(mean[i]), 3),
                 "sd": round(float(sd[i]), 3),
                 "low": round(float(cloud[:, i].min()), 3),
                 "high": round(float(cloud[:, i].max()), 3)}
                for i in order],
            "trajectories": [
                {"future": k + 1,
                 "path": [{"step": h + 1,
                           "cpu_usage": round(float(self.futures[k, h, 0]), 2),
                           "net_out_kbps": round(float(self.futures[k, h, 3]), 2),
                           "packet_rate": round(float(self.futures[k, h, 4]), 2),
                           "conn_attempts": round(float(self.futures[k, h, 5]), 2)}
                          for h in range(self.futures.shape[1])]}
                for k in range(min(6, self.futures.shape[0]))],
        }

    def series(self, feature: str, limit: int = 60) -> List[float]:
        i = FEATURES.index(feature)
        return [round(float(row[i]), 3) for row in list(self.history)[-limit:]]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "observations": self.observations,
            "history": len(self.history),
            "rejected": self.rejected,
            "ready": self.is_ready,
            "fitted": self.predictor.is_fitted,
            "armed": self.has_futures,
            "min_fit": CFG.min_fit,
            "last_consistency": (round(self.last_consistency, 4)
                                 if self.last_consistency is not None else None),
            "last_deviation": (round(self.last_deviation, 3)
                               if self.last_deviation is not None else None),
            "plane_deviation": self.last_plane_deviation,
            "anomalous_planes": self.last_anomalous,
            # Named "baseline", not "state": this is the learned per-feature
            # norm, and calling it "state" collided with the pipeline-wide
            # state payload the console merges on every response.
            "baseline": {FEATURES[i]: round(float(self.ewma_mean[i]), 3)
                         for i in range(N_FEATURES)} if self.observations else {},
        }
