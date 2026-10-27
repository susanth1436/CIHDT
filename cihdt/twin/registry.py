"""STEP 3: one twin per physical device, and the operations the console runs
across all of them.

Deliberately thin.  The registry owns lifecycle and lookup; every judgement
lives in :class:`~cihdt.twin.twin.HolographicTwin`.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import SETTINGS
from ..schemas import Telemetry
from .twin import HolographicTwin


class TwinRegistry:
    """The holographic twin layer of the architecture."""

    def __init__(self, seed: int = SETTINGS.seed) -> None:
        self.seed = seed
        self.twins: Dict[str, HolographicTwin] = {}

    def __len__(self) -> int:
        return len(self.twins)

    def __contains__(self, device_id: object) -> bool:
        return device_id in self.twins

    def get(self, device_id: str) -> Optional[HolographicTwin]:
        return self.twins.get(device_id)

    def create(self, device_id: str, device_type: str) -> HolographicTwin:
        """Instantiate the twin for one device. The STEP 3 action."""
        twin = HolographicTwin(device_id, device_type,
                               seed=self.seed + 31 * (len(self.twins) + 1))
        self.twins[device_id] = twin
        return twin

    def drop(self, device_id: str) -> bool:
        return self.twins.pop(device_id, None) is not None

    # ------------------------------------------------------------ bulk action
    def observe_batch(self, batch: Iterable[Telemetry],
                      trusted: bool = True) -> int:
        """Fold a tick of telemetry into every twin that exists for it."""
        n = 0
        for rec in batch:
            twin = self.twins.get(rec.device_id)
            if twin is not None:
                twin.observe(rec, trusted=trusted)
                n += 1
        return n

    def fit_all(self) -> Dict[str, bool]:
        return {d: t.fit() for d, t in self.twins.items()}

    def arm_all(self, n_futures: int = SETTINGS.twin.n_futures,
                horizon: int = SETTINGS.twin.horizon
                ) -> Dict[str, Any]:
        """Generate and commit futures for every ready twin (STEP 4/5)."""
        armed, skipped = [], []
        for device_id, twin in self.twins.items():
            if twin.is_ready:
                twin.generate_futures(n_futures=n_futures, horizon=horizon)
                armed.append(device_id)
            else:
                skipped.append(device_id)
        return {"armed": armed, "skipped": skipped,
                "n_futures": n_futures, "horizon": horizon}

    def score_batch(self, batch: Iterable[Telemetry]
                    ) -> List[Tuple[Telemetry, Dict[str, Any]]]:
        """Score a tick against each twin's standing commitment (STEP 5)."""
        out = []
        for rec in batch:
            twin = self.twins.get(rec.device_id)
            if twin is None:
                out.append((rec, {"ready": False, "consistency": 1.0,
                                  "deviation": 0.0, "plane_deviation": {},
                                  "anomalous_planes": [],
                                  "channel_deviation": {},
                                  "reason": "no twin"}))
            else:
                out.append((rec, twin.score(rec)))
        return out

    # -------------------------------------------------------------- reporting
    @property
    def ready_count(self) -> int:
        return sum(1 for t in self.twins.values() if t.is_ready)

    @property
    def armed_count(self) -> int:
        return sum(1 for t in self.twins.values() if t.has_futures)

    def snapshot(self) -> List[Dict[str, Any]]:
        return [t.snapshot() for t in self.twins.values()]

    def summary(self) -> Dict[str, Any]:
        return {"count": len(self.twins), "ready": self.ready_count,
                "armed": self.armed_count,
                "min_fit": SETTINGS.twin.min_fit}
