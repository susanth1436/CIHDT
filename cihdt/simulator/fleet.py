"""STEP 1: the fleet the operator assembles by hand, plus the labelled corpus
the edge detector is later trained on.

The fleet is built one device at a time from the console -- the operator picks
a device type from the catalogue and adds it.  Nothing is deployed for them.

``build_corpus`` matters more than it looks.  It generates training data *from
the same profiles as the deployed fleet*, so the model in STEP 6 is trained on
the network it will actually police.  A house of bulbs and sensors has a very
different notion of normal from one with three cameras in it, and a detector
trained on the wrong mix produces false alarms all day.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..schemas import (ATTACK_CLASSES, DEVICE_TYPE_INDEX, DEVICE_TYPES,
                       N_FEATURES, THREAT_INDEX, Telemetry)
from .device import SimulatedDevice
from .profiles import DEVICE_PROFILES

Layout = List[Tuple[str, int]]


class IoTFleet:
    """The operator's home network: an ordered collection of devices."""

    def __init__(self, seed: int = 0) -> None:
        self.seed = seed
        self.devices: Dict[str, SimulatedDevice] = {}
        self._counters: Dict[str, int] = {t: 0 for t in DEVICE_TYPES}
        self.ticks = 0

    # ------------------------------------------------------------ composition
    def add_device(self, device_type: str,
                   label: Optional[str] = None) -> SimulatedDevice:
        """Add one device of the chosen type. This is the STEP 1 action."""
        if device_type not in DEVICE_PROFILES:
            raise ValueError(f"unknown device type {device_type!r}")
        self._counters[device_type] += 1
        n = self._counters[device_type]
        device_id = f"{device_type}_{n:02d}"
        dev = SimulatedDevice(device_id, device_type,
                              seed=self.seed + 17 * len(self.devices) + n,
                              label=label)
        self.devices[device_id] = dev
        return dev

    def remove_device(self, device_id: str) -> bool:
        return self.devices.pop(device_id, None) is not None

    def get(self, device_id: str) -> Optional[SimulatedDevice]:
        return self.devices.get(device_id)

    def __len__(self) -> int:
        return len(self.devices)

    @property
    def layout(self) -> Layout:
        counts: Dict[str, int] = {}
        for dev in self.devices.values():
            counts[dev.device_type] = counts.get(dev.device_type, 0) + 1
        return [(t, counts[t]) for t in DEVICE_TYPES if t in counts]

    # ------------------------------------------------------------------- tick
    def tick(self) -> List[Telemetry]:
        """One observation from every device. Only ever called on demand."""
        self.ticks += 1
        return [dev.tick() for dev in self.devices.values()]

    def collect(self, n_ticks: int) -> List[List[Telemetry]]:
        """Collect ``n_ticks`` batches. The operator chooses ``n_ticks``."""
        return [self.tick() for _ in range(max(0, int(n_ticks)))]

    # -------------------------------------------------------------- reporting
    def status(self) -> List[Dict[str, Any]]:
        return [d.snapshot() for d in self.devices.values()]

    def compromised(self) -> List[str]:
        return [d.device_id for d in self.devices.values() if d.is_compromised]

    def summary(self) -> Dict[str, Any]:
        return {
            "n_devices": len(self.devices),
            "ticks": self.ticks,
            "layout": {t: n for t, n in self.layout},
            "compromised": self.compromised(),
        }


# ---------------------------------------------------------------------------
# Labelled corpus for STEP 6
# ---------------------------------------------------------------------------
def build_corpus(layout: Layout, rows_per_class: int = 380, seed: int = 0,
                 intensity_range: Tuple[float, float] = (0.28, 1.0),
                 classes: Optional[Sequence[str]] = None
                 ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate a labelled telemetry corpus for the given device mix.

    Attack rows are drawn across a *range* of intensities, not just full
    strength.  Training only on loud attacks produces a model that is perfect
    in a demo and blind to anything subtle, which is the failure mode this
    whole project is about.

    Returns ``(X, y, device_type_ids)``.
    """
    if not layout:
        raise ValueError("cannot build a corpus for an empty fleet")

    rng = np.random.default_rng(seed)
    types = [t for t, n in layout for _ in range(max(1, n))]
    class_list = list(classes) if classes else ["normal"] + list(ATTACK_CLASSES)

    # A warm pool of devices per type: warming them first means the corpus
    # inherits the drift and cycle structure of a running network.
    pool: Dict[str, List[SimulatedDevice]] = {}
    for i, dtype in enumerate(sorted(set(types))):
        pool[dtype] = []
        for k in range(3):
            dev = SimulatedDevice(f"corpus_{dtype}_{k}", dtype,
                                  seed=seed + 991 * i + 7 * k)
            for _ in range(12):
                dev.tick()
            pool[dtype].append(dev)

    X_rows: List[np.ndarray] = []
    y_rows: List[int] = []
    dt_rows: List[int] = []

    lo, hi = intensity_range
    for cls in class_list:
        for _ in range(int(rows_per_class)):
            dtype = types[int(rng.integers(len(types)))]
            dev = pool[dtype][int(rng.integers(len(pool[dtype])))]
            if cls == "normal":
                dev.stop_attack()
            else:
                dev.start_attack(cls, duration=3,
                                 intensity=float(rng.uniform(lo, hi)))
            rec = dev.tick()
            X_rows.append(rec.values)
            y_rows.append(THREAT_INDEX[cls])
            dt_rows.append(DEVICE_TYPE_INDEX[dtype])
        for dev_list in pool.values():
            for dev in dev_list:
                dev.stop_attack()

    X = np.asarray(X_rows, dtype=np.float64).reshape(-1, N_FEATURES)
    y = np.asarray(y_rows, dtype=np.int64)
    dt = np.asarray(dt_rows, dtype=np.int64)

    order = rng.permutation(len(y))
    return X[order], y[order], dt[order]
