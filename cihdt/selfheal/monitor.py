"""STEP 12: watching the model's own health, and healing it when it fails.

The hard question here is what "compromised" even means when you have no
labels.  In production nobody tells you an attack was missed.

The answer this module uses is the twin.  The twin and the classifier are
independent detectors of the same events: the twin judges an observation
against the futures it committed to, the classifier judges it against what it
learned.  When they agree, both are probably right.  When the twin keeps
flagging deviations that the classifier calls perfectly normal, one of two
things is true -- and a successfully poisoned classifier is the interesting one.

Crucially the trigger is **degradation, not an absolute rate**.  The two
detectors disagree constantly on low-and-slow attacks, and that disagreement is
ordinary operation rather than evidence of compromise.  What is never ordinary
is the model becoming materially worse than its own established baseline.  A
fixed agreement threshold would fire on a healthy fleet that happens to be
noisy, and stay silent on a poisoned model that was mediocre to begin with.

Healing is rollback, purge, retrain -- in that order, and never in place.  You
cannot subtract poison from a trained model.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional

import numpy as np

from ..config import SETTINGS
from ..schemas import ThreatVerdict

CFG = SETTINGS.heal


@dataclass
class HealthCheck:
    """One assessment of the running model."""
    evaluated: bool
    health_score: float = 1.0
    agreement: Optional[float] = None
    baseline_agreement: Optional[float] = None
    agreement_drop: Optional[float] = None
    detection_rate: Optional[float] = None
    false_negative_rate: Optional[float] = None
    twin_flags: int = 0
    model_flags: int = 0
    both_flagged: int = 0
    window: int = 0
    degraded: bool = False
    reasons: List[str] = field(default_factory=list)
    note: str = ""
    at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "evaluated": self.evaluated,
            "health_score": round(self.health_score, 4),
            "agreement": (round(self.agreement, 4)
                          if self.agreement is not None else None),
            "baseline_agreement": (round(self.baseline_agreement, 4)
                                   if self.baseline_agreement is not None else None),
            "agreement_drop": (round(self.agreement_drop, 4)
                               if self.agreement_drop is not None else None),
            "detection_rate": (round(self.detection_rate, 4)
                               if self.detection_rate is not None else None),
            "false_negative_rate": (round(self.false_negative_rate, 4)
                                    if self.false_negative_rate is not None else None),
            "twin_flags": self.twin_flags,
            "model_flags": self.model_flags,
            "both_flagged": self.both_flagged,
            "window": self.window,
            "degraded": self.degraded,
            "reasons": self.reasons,
            "note": self.note,
            "at": self.at,
        }


class SelfHealingMonitor:
    """Tracks model/twin agreement and drives rollback when it collapses."""

    def __init__(self) -> None:
        self.window: Deque[Dict[str, Any]] = deque(maxlen=CFG.window)
        self.baseline_samples: List[float] = []
        self.baseline: Optional[float] = None
        self.checks: List[HealthCheck] = []
        self.last_check: Optional[HealthCheck] = None
        self.heal_events: List[Dict[str, Any]] = []
        self.observations = 0

    # -------------------------------------------------------------- ingestion
    def record(self, verdict: ThreatVerdict, twin_ready: bool) -> None:
        self.observations += 1
        self.window.append({
            "twin_flag": bool(twin_ready and verdict.twin_flagged),
            "model_flag": verdict.predicted_class != "normal",
            "twin_ready": bool(twin_ready),
            "consistency": verdict.counterfactual_consistency,
            "ts": verdict.timestamp,
        })

    def reset_baseline(self, reason: str = "") -> None:
        """Forget the learned norm. Called whenever the model changes.

        A newly promoted model has its own operating point; judging it against
        its predecessor's baseline would flag every promotion as a compromise.
        """
        self.baseline_samples = []
        self.baseline = None
        self.checks.append(HealthCheck(evaluated=False,
                                       note=f"baseline reset: {reason}"))

    # ------------------------------------------------------------------ check
    def check(self) -> HealthCheck:
        """Assess the model on the current window. The STEP 12 action."""
        rows = list(self.window)
        twin_flags = [r for r in rows if r["twin_flag"]]
        model_flags = [r for r in rows if r["model_flag"]]
        both = [r for r in twin_flags if r["model_flag"]]

        if len(twin_flags) < CFG.min_flags_for_verdict:
            hc = HealthCheck(
                evaluated=False, window=len(rows),
                twin_flags=len(twin_flags), model_flags=len(model_flags),
                both_flagged=len(both),
                note=f"only {len(twin_flags)} twin flags in the window; "
                     f"{CFG.min_flags_for_verdict} are needed to judge. "
                     f"Collect more telemetry, or run an attack to generate some.")
            self.last_check = hc
            self.checks.append(hc)
            return hc

        agreement = len(both) / len(twin_flags)
        fnr = 1.0 - agreement
        detection_rate = min(1.0, len(model_flags) / max(len(twin_flags), 1))

        # Learn the norm from the first few healthy checks of this model.
        if self.baseline is None:
            self.baseline_samples.append(agreement)
            if len(self.baseline_samples) >= CFG.baseline_checks:
                self.baseline = float(np.mean(self.baseline_samples))

        reasons: List[str] = []
        drop = None
        if self.baseline is not None and self.baseline > 1e-6:
            drop = (self.baseline - agreement) / self.baseline
            if drop > CFG.max_agreement_drop:
                reasons.append(
                    f"model/twin agreement fell {drop:.0%} below this model's "
                    f"own baseline of {self.baseline:.2f}")
        if detection_rate < CFG.min_detection_rate:
            reasons.append(
                f"detection rate {detection_rate:.2f} is under the absolute "
                f"floor of {CFG.min_detection_rate:.2f}")
        if fnr > CFG.max_false_negative_rate:
            reasons.append(
                f"{fnr:.0%} of twin-flagged deviations are being called normal "
                f"by the model")

        # Health score: agreement carried by how well it holds against baseline.
        rel = 1.0 if drop is None else float(np.clip(1.0 - drop, 0.0, 1.0))
        health = float(np.clip(0.55 * agreement + 0.45 * rel, 0.0, 1.0))
        if health < CFG.min_health_score:
            reasons.append(f"composite health score {health:.2f} is below "
                           f"{CFG.min_health_score:.2f}")

        hc = HealthCheck(
            evaluated=True, health_score=health, agreement=agreement,
            baseline_agreement=self.baseline, agreement_drop=drop,
            detection_rate=detection_rate, false_negative_rate=fnr,
            twin_flags=len(twin_flags), model_flags=len(model_flags),
            both_flagged=len(both), window=len(rows),
            degraded=bool(reasons), reasons=reasons,
            note=("baseline still being learned "
                  f"({len(self.baseline_samples)}/{CFG.baseline_checks} checks)"
                  if self.baseline is None else ""))
        self.last_check = hc
        self.checks.append(hc)
        return hc

    # ------------------------------------------------------------------- heal
    def heal(self, registry, retrainer, quarantine, reason: str = ""
             ) -> Dict[str, Any]:
        """Roll back to the last trusted model and purge suspect training data.

        Returns a description of what was done.  Retraining afterwards is the
        caller's decision, so the operator can inspect the cleaned pool first.
        """
        current = registry.active_version
        target = (registry.last_trusted_before(current)
                  if current is not None else None)

        event: Dict[str, Any] = {
            "reason": reason,
            "at": time.time(),
            "from_version": current,
            "rolled_back_to": None,
            "rollback_available": False,
            "distrusted": [],
            "purged_rows": 0,
            "purged_sources": [],
        }

        if target is not None:
            registry.distrust(current, reason=reason or "self-heal")
            registry.activate(target.version)
            event["rolled_back_to"] = target.version
            event["rollback_available"] = True
            event["distrusted"] = [current]
        else:
            event["note"] = ("no earlier trusted model exists to roll back to; "
                             "the current model stays in service while the "
                             "pool is cleaned")

        # Remove everything contributed by sources that have anything held in
        # quarantine.  A source that produced one hostile update is not trusted
        # for the ones that slipped through.
        suspect = quarantine.purge_sources()
        if suspect:
            purge = retrainer.purge(sources=suspect,
                                    reason=reason or "self-heal")
            event["purged_rows"] = purge["removed_rows"]
            event["purged_sources"] = suspect
            event["pool_after"] = purge["pool_after"]
        else:
            event["pool_after"] = retrainer.pool_size

        self.reset_baseline("self-heal")
        self.heal_events.append(event)
        return event

    # -------------------------------------------------------------- reporting
    def snapshot(self) -> Dict[str, Any]:
        return {
            "observations": self.observations,
            "window": len(self.window),
            "window_capacity": CFG.window,
            "baseline": (round(self.baseline, 4)
                         if self.baseline is not None else None),
            "baseline_progress": f"{len(self.baseline_samples)}/{CFG.baseline_checks}",
            "last_check": self.last_check.as_dict() if self.last_check else None,
            "checks_run": len([c for c in self.checks if c.evaluated]),
            "heal_events": self.heal_events[-5:][::-1],
            "heals": len(self.heal_events),
            "thresholds": {
                "max_agreement_drop": CFG.max_agreement_drop,
                "min_detection_rate": CFG.min_detection_rate,
                "max_false_negative_rate": CFG.max_false_negative_rate,
                "min_health_score": CFG.min_health_score,
                "min_flags_for_verdict": CFG.min_flags_for_verdict,
            },
        }
