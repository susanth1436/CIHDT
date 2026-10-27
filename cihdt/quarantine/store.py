"""STEP 10: the quarantine zone.

A quarantined update is not deleted.  That is the whole point of a quarantine
rather than a bin: the update is held intact, with the report that condemned
it, so that it can be dissected now and re-judged later.

Re-judgement matters more than it sounds.  The gate that rejected an update is
only as good as the bank it was scored against, and the bank improves every
round as the twins learn the fleet.  An update quarantined by a thin early bank
may be perfectly honest, and once a better bank exists the operator can rescore
the whole zone and release what no longer looks hostile.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..schemas import ModelUpdate, ValidationReport


@dataclass
class QuarantineRecord:
    """One held update, its verdict, and everything learned about it since."""
    update: ModelUpdate
    report: ValidationReport
    held_at: float = field(default_factory=time.time)
    released: bool = False
    released_at: Optional[float] = None
    release_reason: str = ""
    analysis: Optional[Dict[str, Any]] = None
    rescores: List[float] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "update_id": self.update.update_id,
            "source": self.update.source,
            "n_samples": self.update.n_samples,
            "labels": self.update.label_summary(),
            "declared_strategy": self.update.declared_strategy,
            "meta": self.update.meta,
            "held_at": self.held_at,
            "released": self.released,
            "released_at": self.released_at,
            "release_reason": self.release_reason,
            "rescores": [round(s, 4) for s in self.rescores],
            "analysed": self.analysis is not None,
            "report": self.report.as_dict(),
        }

    def brief(self) -> Dict[str, Any]:
        return {
            "update_id": self.update.update_id,
            "source": self.update.source,
            "n_samples": self.update.n_samples,
            "consistency_score": self.report.consistency_score,
            "threshold": self.report.threshold,
            "suspected_strategy": self.report.suspected_strategy,
            "strategy_confidence": self.report.strategy_confidence,
            "declared_strategy": self.update.declared_strategy,
            "held_at": self.held_at,
            "released": self.released,
            "analysed": self.analysis is not None,
            "rescores": [round(s, 4) for s in self.rescores],
        }


class QuarantineZone:
    """Holds suspicious updates out of the training pool until judged."""

    def __init__(self) -> None:
        self.records: Dict[str, QuarantineRecord] = {}
        self.total_quarantined = 0
        self.total_released = 0

    def add(self, update: ModelUpdate, report: ValidationReport
            ) -> QuarantineRecord:
        rec = QuarantineRecord(update=update, report=report)
        self.records[update.update_id] = rec
        self.total_quarantined += 1
        return rec

    def get(self, update_id: str) -> Optional[QuarantineRecord]:
        return self.records.get(update_id)

    def held(self) -> List[QuarantineRecord]:
        return [r for r in self.records.values() if not r.released]

    def all(self) -> List[QuarantineRecord]:
        return list(self.records.values())

    def release(self, update_id: str, reason: str = "operator release"
                ) -> Optional[QuarantineRecord]:
        """Let an update out of quarantine and into the safe pool."""
        rec = self.records.get(update_id)
        if rec is None or rec.released:
            return None
        rec.released = True
        rec.released_at = time.time()
        rec.release_reason = reason
        self.total_released += 1
        return rec

    def purge_sources(self) -> List[str]:
        """Sources that contributed anything still held. Used by self-healing."""
        return sorted({r.update.source for r in self.held()})

    def rescore(self, validator, bank, incumbent, core_X, core_y, core_dt,
                auto_release: bool = False) -> Dict[str, Any]:
        """Re-run validation on everything held, against the current bank.

        Nothing is released automatically unless the operator asks for it; the
        default is to report what *would* now pass and let a human decide.
        """
        would_pass, still_held = [], []
        for rec in self.held():
            report = validator.validate(rec.update, bank, incumbent,
                                        core_X, core_y, core_dt)
            rec.rescores.append(report.consistency_score)
            if report.decision == "ACCEPTED":
                would_pass.append(rec.update.update_id)
                rec.report = report
                if auto_release:
                    self.release(rec.update.update_id,
                                 reason="cleared on rescore against a newer bank")
            else:
                still_held.append(rec.update.update_id)
        return {"rescored": len(would_pass) + len(still_held),
                "would_pass": would_pass, "still_held": still_held,
                "auto_released": auto_release}

    def strategy_counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for rec in self.records.values():
            k = rec.report.suspected_strategy
            out[k] = out.get(k, 0) + 1
        return out

    def snapshot(self) -> Dict[str, Any]:
        held = self.held()
        return {
            "held": len(held),
            "total_quarantined": self.total_quarantined,
            "total_released": self.total_released,
            "by_suspected_strategy": self.strategy_counts(),
            "records": [r.brief() for r in
                        sorted(self.records.values(),
                               key=lambda r: r.held_at, reverse=True)],
        }
