"""STEP 7: crafting the poisoned training contributions the defence is tested
against.

Five strategies, chosen because they attack the defence in genuinely different
ways rather than because they make a long list:

``label_flip``      the blunt instrument.  Attack rows relabelled normal.
``clean_label``     labels untouched, *features* dragged toward benign.  Beats
                    every label-distribution check, because the labels are
                    honest.
``gradual``         a small flip fraction, repeated over rounds.  Any single
                    update is statistically unremarkable; the damage is in the
                    accumulation.
``backdoor``        a rare trigger pattern is stamped onto attack rows and
                    labelled normal.  Overall accuracy is barely dented, so
                    accuracy-based gates wave it straight through.
``sybil``           the payload is split across many small updates from many
                    invented sources, so no single contribution is large enough
                    to look worth auditing.

Every crafted update carries its ``declared_strategy``, which exists purely so
the console can score the defence afterwards.  The validator never reads it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import SETTINGS
from ..schemas import (ATTACK_STRATEGIES, FEATURES, NORMAL_IDX, ModelUpdate,
                       clamp_features, new_id)
from ..simulator.profiles import ATTACK_PROFILES

# The backdoor trigger: a combination that essentially never occurs naturally,
# cheap for an attacker to reproduce at inference time, and small enough to
# hide inside otherwise ordinary rows.
BACKDOOR_TRIGGER: Dict[str, float] = {
    "port_diversity": 7.0,
    "payload_entropy": 4.44,
    "reconnects": 3.0,
    "avg_pkt_size": 404.0,
}

STRATEGY_TEXT: Dict[str, Dict[str, str]] = {
    "clean": {
        "label": "Honest contribution",
        "detail": "An unmodified sample of validated telemetry. This is the "
                  "control case: it should be accepted.",
    },
    "label_flip": {
        "label": "Label flipping",
        "detail": "Attack rows are relabelled as normal. Crude, high-impact, "
                  "and the easiest strategy for any defence to catch.",
    },
    "gradual_poisoning": {
        "label": "Gradual poisoning",
        "detail": "A small fraction of labels is flipped and the features are "
                  "nudged benign. One update looks fine; twenty do not.",
    },
    "backdoor": {
        "label": "Backdoor trigger",
        "detail": "A rare feature pattern is stamped onto attack rows and "
                  "labelled normal, teaching the model a secret bypass.",
    },
    "sybil": {
        "label": "Sybil update flood",
        "detail": "The payload is split across many small updates from many "
                  "invented device identities.",
    },
    "clean_label": {
        "label": "Clean-label poisoning",
        "detail": "Every label is honest. Genuinely-normal rows are perturbed "
                  "toward an attack signature, widening the benign region "
                  "until the attack fits inside it.",
    },
}


class PoisonForge:
    """Builds honest and poisoned :class:`ModelUpdate` objects."""

    def __init__(self, seed: int = SETTINGS.seed) -> None:
        self.rng = np.random.default_rng(seed)
        self.crafted = 0

    # ------------------------------------------------------------- sampling
    def _sample(self, X: np.ndarray, y: np.ndarray, dt: np.ndarray, n: int
                ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = int(min(max(10, n), len(y)))
        idx = self.rng.choice(len(y), n, replace=False)
        return X[idx].copy(), y[idx].copy(), dt[idx].copy()

    def _benign_centroid(self, X: np.ndarray, y: np.ndarray) -> np.ndarray:
        benign = X[y == NORMAL_IDX]
        return (benign.mean(axis=0) if len(benign)
                else X.mean(axis=0))

    # ------------------------------------------------------------- honest
    def clean_update(self, X: np.ndarray, y: np.ndarray, dt: np.ndarray,
                     source: str, n: int = 240,
                     round_index: int = 0) -> ModelUpdate:
        sx, sy, sdt = self._sample(X, y, dt, n)
        self.crafted += 1
        return ModelUpdate.new(source, sx, sy, sdt, declared_strategy="clean",
                               round_index=round_index,
                               meta={"note": "unmodified validated telemetry"})

    # ------------------------------------------------------------- poisoned
    def craft(self, strategy: str, X: np.ndarray, y: np.ndarray,
              dt: np.ndarray, source: str, n: int = 240,
              round_index: int = 0,
              potency: float = 1.0) -> List[ModelUpdate]:
        """Craft one strategy. Returns a list because sybil produces many.

        ``potency`` in (0, 1] scales how aggressive the attack is, so the
        operator can explore the stealth/impact trade-off from the console.
        """
        if strategy == "clean":
            return [self.clean_update(X, y, dt, source, n, round_index)]
        if strategy not in ATTACK_STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        p = float(np.clip(potency, 0.05, 1.0))
        fn = getattr(self, f"_{strategy}")
        updates = fn(X, y, dt, source, n, round_index, p)
        self.crafted += len(updates)
        return updates

    # -- label flip ---------------------------------------------------------
    def _label_flip(self, X, y, dt, source, n, round_index, p) -> List[ModelUpdate]:
        sx, sy, sdt = self._sample(X, y, dt, n)
        attack_idx = np.flatnonzero(sy != NORMAL_IDX)
        k = int(len(attack_idx) * (0.35 + 0.45 * p))
        flip = self.rng.choice(attack_idx, min(k, len(attack_idx)),
                               replace=False) if len(attack_idx) else []
        sy[flip] = NORMAL_IDX
        return [ModelUpdate.new(
            source, sx, sy, sdt, declared_strategy="label_flip",
            round_index=round_index,
            meta={"flipped": int(len(flip)),
                  "flip_fraction": round(len(flip) / max(len(sy), 1), 3)})]

    # -- gradual ------------------------------------------------------------
    def _gradual_poisoning(self, X, y, dt, source, n, round_index, p
                           ) -> List[ModelUpdate]:
        sx, sy, sdt = self._sample(X, y, dt, n)
        centroid = self._benign_centroid(X, y)
        attack_idx = np.flatnonzero(sy != NORMAL_IDX)
        k = int(len(attack_idx) * (0.08 + 0.14 * p))
        chosen = (self.rng.choice(attack_idx, min(k, len(attack_idx)),
                                  replace=False) if len(attack_idx) else [])
        # Flip a few labels, and shade the corresponding features benign so the
        # rows are not obvious outliers in their new class.
        pull = 0.30 * p
        sx[chosen] = clamp_features(sx[chosen] * (1 - pull) + centroid * pull)
        sy[chosen] = NORMAL_IDX
        return [ModelUpdate.new(
            source, sx, sy, sdt, declared_strategy="gradual_poisoning",
            round_index=round_index,
            meta={"flipped": int(len(chosen)), "feature_pull": round(pull, 3),
                  "flip_fraction": round(len(chosen) / max(len(sy), 1), 3)})]

    # -- backdoor -----------------------------------------------------------
    def _backdoor(self, X, y, dt, source, n, round_index, p) -> List[ModelUpdate]:
        sx, sy, sdt = self._sample(X, y, dt, n)
        attack_idx = np.flatnonzero(sy != NORMAL_IDX)
        k = int(len(attack_idx) * (0.30 + 0.35 * p))
        chosen = (self.rng.choice(attack_idx, min(k, len(attack_idx)),
                                  replace=False) if len(attack_idx) else [])
        for feature, value in BACKDOOR_TRIGGER.items():
            i = FEATURES.index(feature)
            sx[chosen, i] = value * (1.0 + self.rng.normal(0, 0.01, len(chosen)))
        sy[chosen] = NORMAL_IDX
        return [ModelUpdate.new(
            source, clamp_features(sx), sy, sdt, declared_strategy="backdoor",
            round_index=round_index,
            meta={"triggered": int(len(chosen)),
                  "trigger": BACKDOOR_TRIGGER,
                  "flip_fraction": round(len(chosen) / max(len(sy), 1), 3)})]

    # -- clean label --------------------------------------------------------
    def _clean_label(self, X, y, dt, source, n, round_index, p,
                     target: Optional[str] = None) -> List[ModelUpdate]:
        """Perturb genuinely-normal rows toward an attack, keeping them normal.

        This is the textbook clean-label attack, and the direction matters.
        Every label in this update is honest -- no row was relabelled, so any
        label-distribution check passes it without comment.  What has been
        moved is the *feature space*: normal rows are dragged partway toward
        one attack's signature, so the model learns that elevated port counts
        and connection rates are ordinary.  The decision boundary is pushed
        outward, and the attacker walks through the gap it leaves.
        """
        sx, sy, sdt = self._sample(X, y, dt, n)
        attack = target or str(self.rng.choice(list(ATTACK_PROFILES)))
        benign_idx = np.flatnonzero(sy == NORMAL_IDX)

        # Deliberately partial. At full strength the rows would be obvious
        # attacks wearing a normal label; the point of clean-label poisoning is
        # to sit in the ambiguous band just inside the boundary.
        strength = (0.18 + 0.30 * p) * self.rng.uniform(
            0.7, 1.3, size=(len(benign_idx), 1))
        rows = sx[benign_idx]
        for feature, (mult, add) in ATTACK_PROFILES[attack].items():
            i = FEATURES.index(feature)
            col = rows[:, i:i + 1]
            rows[:, i:i + 1] = col * (1.0 + (mult - 1.0) * strength) + add * strength
        sx[benign_idx] = clamp_features(rows)

        return [ModelUpdate.new(
            source, sx, sy, sdt, declared_strategy="clean_label",
            round_index=round_index,
            meta={"perturbed": int(len(benign_idx)),
                  "toward_attack": attack,
                  "mean_strength": round(float(strength.mean()), 3),
                  "flip_fraction": 0.0})]

    # -- sybil --------------------------------------------------------------
    def _sybil(self, X, y, dt, source, n, round_index, p) -> List[ModelUpdate]:
        shards = int(4 + round(4 * p))
        per = max(20, n // shards)
        group = new_id("sybil")
        out: List[ModelUpdate] = []
        for i in range(shards):
            sx, sy, sdt = self._sample(X, y, dt, per)
            attack_idx = np.flatnonzero(sy != NORMAL_IDX)
            k = int(len(attack_idx) * (0.20 + 0.25 * p))
            flip = (self.rng.choice(attack_idx, min(k, len(attack_idx)),
                                    replace=False) if len(attack_idx) else [])
            sy[flip] = NORMAL_IDX
            out.append(ModelUpdate.new(
                f"{source}~sybil{i + 1:02d}", sx, sy, sdt,
                declared_strategy="sybil", round_index=round_index,
                meta={"sybil_group": group, "shard": i + 1, "shards": shards,
                      "flipped": int(len(flip)),
                      "flip_fraction": round(len(flip) / max(len(sy), 1), 3)}))
        return out
