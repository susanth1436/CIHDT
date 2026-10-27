"""STEP 6: the edge threat-detection model.

A random forest, and that is a considered choice rather than a shortcut.  It
trains in a second on a laptop-class edge box, needs no GPU, gives calibrated
class probabilities out of the box, and -- the part that matters for this
project -- can be retrained from scratch on every round.  That last property is
what makes the self-healing rollback in STEP 12 possible at all: you cannot
un-learn poison from a neural network's weights, but you can throw away a
forest and grow a new one from a cleaned pool in under two seconds.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score

from ..config import SETTINGS
from ..schemas import (NORMAL_IDX, THREAT_CLASSES, Telemetry, ThreatVerdict,
                       risk_from_confidence)
from .features import FEATURE_NAMES, engineer

CFG = SETTINGS.detect


class ThreatDetector:
    """Multi-class threat classifier over engineered telemetry features."""

    def __init__(self, seed: int = SETTINGS.seed, version: int = 0,
                 n_estimators: int = CFG.n_estimators,
                 class_weight: object = "__default__") -> None:
        self.seed = seed
        self.version = version
        self.n_estimators = int(n_estimators)
        # Shadow and probe models pass ``class_weight=None`` deliberately:
        # rebalancing would partly undo the very label skew a poisoned update
        # introduced, which is the thing we are trying to measure.
        self.class_weight = (CFG.class_weight if class_weight == "__default__"
                             else class_weight)
        self.model: Optional[RandomForestClassifier] = None
        self.classes_: np.ndarray = np.array([], dtype=np.int64)
        self.trained_at: Optional[float] = None
        self.n_train = 0

    @property
    def is_fitted(self) -> bool:
        return self.model is not None

    # -------------------------------------------------------------------- fit
    def fit(self, X: np.ndarray, y: np.ndarray,
            device_type_ids: Optional[np.ndarray] = None,
            sample_weight: Optional[np.ndarray] = None) -> "ThreatDetector":
        Xe = engineer(X, device_type_ids)
        y = np.asarray(y, dtype=np.int64)
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators, max_depth=CFG.max_depth,
            min_samples_leaf=CFG.min_samples_leaf,
            class_weight=self.class_weight, random_state=self.seed,
            n_jobs=-1)
        self.model.fit(Xe, y, sample_weight=sample_weight)
        self.classes_ = self.model.classes_.astype(np.int64)
        self.trained_at = time.time()
        self.n_train = int(len(y))
        return self

    # ---------------------------------------------------------------- predict
    def predict_proba(self, X: np.ndarray,
                      device_type_ids: Optional[np.ndarray] = None
                      ) -> np.ndarray:
        """Probabilities over the *full* threat taxonomy, (n, 7).

        The forest only knows the classes it was trained on; a poisoned update
        that erases a class entirely would otherwise silently change the shape
        of everything downstream.  Projecting back onto the full taxonomy keeps
        every consumer of this model on stable ground.
        """
        if self.model is None:
            raise RuntimeError("detector is not fitted")
        raw = self.model.predict_proba(engineer(X, device_type_ids))
        full = np.zeros((raw.shape[0], len(THREAT_CLASSES)))
        for j, cls in enumerate(self.classes_):
            full[:, int(cls)] = raw[:, j]
        return full

    def predict(self, X: np.ndarray,
                device_type_ids: Optional[np.ndarray] = None) -> np.ndarray:
        return self.predict_proba(X, device_type_ids).argmax(axis=1)

    def verdict(self, rec: Telemetry, consistency: float = 1.0,
                plane_deviation: Optional[Dict[str, float]] = None,
                anomalous_planes: Optional[List[str]] = None,
                twin_flagged: bool = False) -> ThreatVerdict:
        """Score one live observation and package an operator-facing verdict."""
        from ..schemas import DEVICE_TYPE_INDEX
        dt = np.array([DEVICE_TYPE_INDEX.get(rec.device_type, -1)])
        probs = self.predict_proba(rec.values.reshape(1, -1), dt)[0]
        idx = int(probs.argmax())
        predicted = THREAT_CLASSES[idx]
        confidence = float(probs[idx])
        return ThreatVerdict(
            device_id=rec.device_id,
            predicted_class=predicted,
            confidence=confidence,
            risk_level=risk_from_confidence(predicted, confidence),
            probabilities={THREAT_CLASSES[i]: round(float(p), 4)
                           for i, p in enumerate(probs) if p > 0.001},
            counterfactual_consistency=round(float(consistency), 4),
            plane_deviation=plane_deviation or {},
            anomalous_planes=anomalous_planes or [],
            twin_flagged=bool(twin_flagged),
            model_version=self.version,
            ground_truth=rec.ground_truth,
        )

    # --------------------------------------------------------------- evaluate
    def evaluate(self, X: np.ndarray, y: np.ndarray,
                 device_type_ids: Optional[np.ndarray] = None
                 ) -> Dict[str, Any]:
        """Full report card, including the two rates the gates care about.

        ``false_positive_rate`` -- benign traffic called an attack.  Drives the
        operator mad and gets the system switched off.
        ``false_negative_rate`` -- an attack called benign.  The failure mode
        poisoning is designed to produce, so it is the one to watch.
        """
        y = np.asarray(y, dtype=np.int64)
        pred = self.predict(X, device_type_ids)
        labels = list(range(len(THREAT_CLASSES)))
        cm = confusion_matrix(y, pred, labels=labels)

        benign = y == NORMAL_IDX
        attack = ~benign
        fpr = (float((pred[benign] != NORMAL_IDX).mean())
               if benign.any() else 0.0)
        fnr = (float((pred[attack] == NORMAL_IDX).mean())
               if attack.any() else 0.0)

        per_class = {}
        for i, name in enumerate(THREAT_CLASSES):
            mask = y == i
            per_class[name] = {
                "support": int(mask.sum()),
                "recall": round(float((pred[mask] == i).mean()), 4)
                          if mask.any() else None,
            }

        return {
            "accuracy": round(float((pred == y).mean()), 4),
            "macro_f1": round(float(f1_score(y, pred, average="macro",
                                             labels=labels, zero_division=0)), 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
            "attack_recall": round(float((pred[attack] != NORMAL_IDX).mean()), 4)
                             if attack.any() else None,
            "n_eval": int(len(y)),
            "per_class": per_class,
            "confusion": cm.tolist(),
            "labels": THREAT_CLASSES,
        }

    def importances(self, top: int = 12) -> List[Dict[str, Any]]:
        if self.model is None:
            return []
        imp = self.model.feature_importances_
        order = np.argsort(-imp)[:top]
        return [{"feature": FEATURE_NAMES[i], "importance": round(float(imp[i]), 4)}
                for i in order]

    # ------------------------------------------------------------ persistence
    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "classes": self.classes_,
                     "version": self.version, "seed": self.seed,
                     "class_weight": self.class_weight,
                     "n_train": self.n_train, "trained_at": self.trained_at},
                    path)
        return path

    @staticmethod
    def load(path: Path) -> "ThreatDetector":
        blob = joblib.load(path)
        det = ThreatDetector(seed=blob.get("seed", SETTINGS.seed),
                             version=blob.get("version", 0))
        det.class_weight = blob.get("class_weight", CFG.class_weight)
        det.model = blob["model"]
        det.classes_ = blob["classes"]
        det.n_train = blob.get("n_train", 0)
        det.trained_at = blob.get("trained_at")
        return det
