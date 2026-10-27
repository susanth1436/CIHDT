"""STEP 1: a single simulated consumer IoT device.

Each device emits one :class:`Telemetry` record per tick.  Three things are
layered on top of the static profile so the data is not trivially separable:

* a slow **activity cycle**, standing in for day/night usage, so "normal" is a
  moving target rather than a fixed point;
* a **random-walk drift** on the device baseline, so two cameras of the same
  model are never numerically identical;
* per-tick Gaussian noise scaled by each feature's own spread.

A device is healthy until the operator explicitly attacks it.  Nothing turns
hostile on its own -- in this build every attack is launched by hand from the
console, which is the whole point of the manual workflow.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional

import numpy as np

from ..schemas import (FEATURES, N_FEATURES, Telemetry, clamp_features)
from .profiles import ATTACK_PROFILES, DEVICE_PROFILES


class SimulatedDevice:
    """One physical device on the simulated home network."""

    def __init__(self, device_id: str, device_type: str,
                 seed: int = 0, label: Optional[str] = None) -> None:
        if device_type not in DEVICE_PROFILES:
            raise ValueError(f"unknown device type {device_type!r}")
        self.device_id = device_id
        self.device_type = device_type
        self.label = label or device_id
        self.rng = np.random.default_rng(seed)

        profile = DEVICE_PROFILES[device_type]
        self.mu = np.array([profile[f][0] for f in FEATURES], dtype=np.float64)
        self.sigma = np.array([profile[f][1] for f in FEATURES],
                              dtype=np.float64)

        # Per-unit personality: a permanent few-percent offset from the model
        # baseline, so twins have something device-specific to learn.
        self.unit_bias = 1.0 + self.rng.normal(0.0, 0.045, N_FEATURES)
        self.drift = np.zeros(N_FEATURES)
        self.phase = float(self.rng.uniform(0, 2 * math.pi))

        self.sequence = 0
        self.attack: Optional[str] = None
        self.attack_ticks_left = 0
        self.attack_total = 0
        self.intensity = 1.0
        self.created_at = time.time()
        self.last: Optional[Telemetry] = None

    # ------------------------------------------------------------------ state
    @property
    def is_compromised(self) -> bool:
        return self.attack is not None and self.attack_ticks_left > 0

    @property
    def ground_truth(self) -> str:
        return self.attack if self.is_compromised else "normal"

    def start_attack(self, attack: str, duration: int = 25,
                     intensity: float = 1.0) -> None:
        """STEP 6 setup: put this device under a named attack, by hand."""
        if attack not in ATTACK_PROFILES:
            raise ValueError(f"unknown attack {attack!r}")
        self.attack = attack
        self.attack_ticks_left = max(1, int(duration))
        self.attack_total = self.attack_ticks_left
        self.intensity = float(np.clip(intensity, 0.02, 1.0))

    def stop_attack(self) -> None:
        self.attack = None
        self.attack_ticks_left = 0
        self.attack_total = 0

    # ------------------------------------------------------------------- tick
    def tick(self) -> Telemetry:
        """Produce one observation and advance the device's internal clock."""
        self.sequence += 1

        # Slow activity cycle: a full period every ~180 ticks.
        cycle = 1.0 + 0.18 * math.sin(self.phase + self.sequence / 28.6)
        # Mean-reverting random walk on the baseline.
        self.drift = 0.94 * self.drift + self.rng.normal(0.0, 0.012, N_FEATURES)

        base = self.mu * self.unit_bias * cycle * (1.0 + self.drift)
        values = base + self.rng.normal(0.0, 1.0, N_FEATURES) * self.sigma

        if self.is_compromised:
            values = self._deform(values)
            self.attack_ticks_left -= 1
            if self.attack_ticks_left <= 0:
                self.attack_ticks_left = 0

        # Counts are integers in the real world; rounding them stops the model
        # cheating on fractional values no packet counter would ever report.
        values = clamp_features(values)
        for name in ("conn_attempts", "failed_logins", "unique_dst_ips",
                     "port_diversity", "reconnects"):
            i = FEATURES.index(name)
            values[i] = float(max(0.0, round(values[i])))

        rec = Telemetry(device_id=self.device_id, device_type=self.device_type,
                        timestamp=time.time(), values=values,
                        ground_truth=self.ground_truth, sequence=self.sequence)
        self.last = rec
        return rec

    def _deform(self, values: np.ndarray) -> np.ndarray:
        """Apply the current attack's deformation at the chosen intensity.

        The first few ticks ramp in, because real attacks do not reach full
        volume instantly, and a detector that only fires at peak intensity is
        no use to anybody.
        """
        assert self.attack is not None
        elapsed = self.attack_total - self.attack_ticks_left
        ramp = min(1.0, 0.35 + 0.65 * (elapsed / 4.0))
        strength = self.intensity * ramp

        out = values.copy()
        for feature, (mult, add) in ATTACK_PROFILES[self.attack].items():
            i = FEATURES.index(feature)
            out[i] = out[i] * (1.0 + (mult - 1.0) * strength) + add * strength
        # Attack traffic is machine-generated, so it is *less* noisy than human
        # traffic; a touch of jitter keeps it from being perfectly separable.
        out *= 1.0 + self.rng.normal(0.0, 0.05, N_FEATURES)
        return out

    # -------------------------------------------------------------- reporting
    def snapshot(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "label": self.label,
            "sequence": self.sequence,
            "compromised": self.is_compromised,
            "attack": self.attack if self.is_compromised else None,
            "attack_ticks_left": int(self.attack_ticks_left),
            "attack_total": int(self.attack_total),
            "intensity": round(self.intensity, 3) if self.is_compromised else None,
            "ground_truth": self.ground_truth,
            "last": self.last.as_dict() if self.last is not None else None,
        }
