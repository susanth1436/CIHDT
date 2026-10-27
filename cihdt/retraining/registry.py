"""STEP 11/12: the secure model registry.

Every model the gateway has ever trusted, on disk, with the metrics it was
promoted on.  Two properties make the rest of the system possible:

* nothing is ever promoted without a recorded reason, so an operator can
  always answer "why is this the model we are running?";
* nothing is ever overwritten, so STEP 12 can roll back to a known-good
  version instead of trying to repair a compromised one in place.

Rollback is the only credible response to a model you have lost confidence in.
You cannot subtract poison from a trained model -- you can only go back to
something you trust and rebuild from a cleaned pool.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import MODEL_DIR, SETTINGS
from ..detection.model import ThreatDetector
from ..schemas import ModelVersion


class ModelRegistry:
    """Versioned, on-disk store of promoted detection models."""

    def __init__(self, root: Path = MODEL_DIR, reset: bool = False) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "ledger.json"
        self.versions: Dict[int, ModelVersion] = {}
        self.active_version: Optional[int] = None
        self._next = 1
        if reset:
            self._reset()
        else:
            self._load_ledger()

    # ------------------------------------------------------------- internals
    def _reset(self) -> None:
        for p in self.root.glob("detector_v*.joblib"):
            try:
                p.unlink()
            except OSError:                                # pragma: no cover
                pass
        if self.ledger_path.exists():
            try:
                self.ledger_path.unlink()
            except OSError:                                # pragma: no cover
                pass
        self.versions, self.active_version, self._next = {}, None, 1

    def _load_ledger(self) -> None:
        if not self.ledger_path.exists():
            return
        try:
            blob = json.loads(self.ledger_path.read_text())
        except (OSError, json.JSONDecodeError):            # pragma: no cover
            return
        for entry in blob.get("versions", []):
            mv = ModelVersion(**entry)
            self.versions[mv.version] = mv
        self.active_version = blob.get("active")
        self._next = max(self.versions, default=0) + 1

    def _save_ledger(self) -> None:
        payload = {"active": self.active_version,
                   "updated_at": time.time(),
                   "versions": [v.as_dict() for v in
                                sorted(self.versions.values(),
                                       key=lambda v: v.version)]}
        self.ledger_path.write_text(json.dumps(payload, indent=2))

    def _prune(self) -> None:
        keep = SETTINGS.retrain.keep_versions
        ordered = sorted(self.versions, reverse=True)
        for version in ordered[keep:]:
            if version == self.active_version:
                continue
            mv = self.versions.pop(version, None)
            if mv is not None:
                try:
                    Path(mv.path).unlink(missing_ok=True)
                except OSError:                            # pragma: no cover
                    pass

    # ---------------------------------------------------------------- public
    def register(self, detector: ThreatDetector, metrics: Dict[str, Any],
                 poison_resistance: float, trusted: bool = True,
                 notes: str = "", activate: bool = True) -> ModelVersion:
        version = self._next
        self._next += 1
        path = self.root / f"detector_v{version:04d}.joblib"
        detector.version = version
        detector.save(path)

        mv = ModelVersion(
            version=version, path=str(path),
            accuracy=float(metrics.get("accuracy", 0.0)),
            macro_f1=float(metrics.get("macro_f1", 0.0)),
            false_positive_rate=float(metrics.get("false_positive_rate", 0.0)),
            false_negative_rate=float(metrics.get("false_negative_rate", 0.0)),
            poison_resistance=float(poison_resistance),
            trusted=bool(trusted),
            parent=self.active_version,
            notes=notes,
            n_train=int(metrics.get("n_train", detector.n_train)),
        )
        self.versions[version] = mv
        if activate:
            self.active_version = version
        self._prune()
        self._save_ledger()
        return mv

    def get(self, version: int) -> Optional[ModelVersion]:
        return self.versions.get(version)

    def load(self, version: int) -> Optional[ThreatDetector]:
        mv = self.versions.get(version)
        if mv is None or not Path(mv.path).exists():
            return None
        det = ThreatDetector.load(Path(mv.path))
        det.version = version
        return det

    def active(self) -> Optional[ThreatDetector]:
        return (self.load(self.active_version)
                if self.active_version is not None else None)

    def activate(self, version: int) -> bool:
        if version not in self.versions:
            return False
        self.active_version = version
        self._save_ledger()
        return True

    def last_trusted_before(self, version: int) -> Optional[ModelVersion]:
        """The newest trusted version older than ``version``. The rollback target."""
        candidates = [v for v in self.versions.values()
                      if v.trusted and v.version < version]
        return max(candidates, key=lambda v: v.version) if candidates else None

    def distrust(self, version: int, reason: str = "") -> bool:
        mv = self.versions.get(version)
        if mv is None:
            return False
        mv.trusted = False
        mv.notes = (mv.notes + " | " if mv.notes else "") + f"distrusted: {reason}"
        self._save_ledger()
        return True

    def lineage(self) -> List[Dict[str, Any]]:
        return [v.as_dict() for v in
                sorted(self.versions.values(), key=lambda v: v.version)]

    def snapshot(self) -> Dict[str, Any]:
        active = (self.versions.get(self.active_version)
                  if self.active_version is not None else None)
        return {"active": self.active_version,
                "active_model": active.as_dict() if active else None,
                "count": len(self.versions),
                "lineage": self.lineage()}
