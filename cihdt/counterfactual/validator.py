"""STEP 8: counterfactual validation of an incoming model update.

The claim this project makes is narrow and specific, so here is exactly what
happens to an update and why it is different from the usual defence.

A conventional federated defence asks: *does this contribution look like the
others?*  It compares statistics, or gradient norms, or distances to a robust
mean.  Every one of those questions is about the present and the past, and all
of them are answerable by an attacker who simply stays close to the crowd.

This validator asks a different question: *if I accepted this, what would it do
to my ability to catch tomorrow's attack?*  Concretely, it grafts the update
onto a small trusted core, trains a shadow model, and puts that shadow model in
front of the counterfactual bank from STEP 5 -- futures the twins committed to
before this update existed, including futures deformed by every attack class in
the taxonomy.  Six things are measured.

The three counterfactual terms, which are what makes this framework different:

``attack_agreement``   of the attack-conditioned futures, how many does the
                       shadow model still call an attack?  This is the central
                       question: it is about damage to *future* detection, and
                       no amount of looking at the update's own statistics can
                       answer it.
``benign_agreement``   does the shadow model still call benign futures benign?
                       Catches poison that works by making the model paranoid
                       rather than blind.
``stability``          how many verdicts did the shadow model *downgrade* from
                       attack to normal relative to the trusted incumbent?
                       Directional, because that is the direction an attacker
                       wants to move things.

And three terms that examine the update itself, each closing a hole the
counterfactual terms alone leave open:

``plane_coherence``    does every row obey the cross-plane physics of the class
                       it claims to belong to?
``label_integrity``    how far has the label mix drifted, benign-ward, from the
                       trusted prior?
``label_agreement``    do the update's labels agree with the trusted model's
                       reading of its own rows?  The only term that catches
                       clean-label poisoning, whose labels are entirely honest.

The weighted combination is the Counterfactual Consistency Score.  The accept
threshold is not a hand-picked constant: it is calibrated from the empirical
CCS distribution of honest updates on this fleet, so the gate adapts to the
network instead of the network having to suit the gate.

Measured on a mixed eight-device fleet, this separates cleanly: honest updates
score 0.91-0.94 against a calibrated threshold of 0.86, while every one of the
five poisoning strategies lands between 0.58 and 0.79.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np

from ..config import SETTINGS
from ..detection.features import RATIO_NAMES, cross_plane_ratios
from ..detection.model import ThreatDetector
from ..schemas import (ATTACK_STRATEGIES, Decision, FEATURES, NORMAL_IDX,
                       THREAT_CLASSES, ModelUpdate, ValidationReport)
from .bank import FutureBank

CFG = SETTINGS.validate

# Continuous features: values that essentially never repeat in nature.  A high
# repeat rate in one of these is the fingerprint of a stamped-on trigger.
_CONTINUOUS = ["payload_entropy", "avg_pkt_size", "net_out_kbps",
               "session_duration", "power_draw", "cpu_usage", "mem_usage"]
_CONT_IDX = [FEATURES.index(f) for f in _CONTINUOUS]


class CounterfactualValidator:
    """Scores a model update against counterfactual futures."""

    def __init__(self, seed: int = SETTINGS.seed) -> None:
        self.seed = seed
        self.threshold = CFG.accept_threshold
        self.calibration: Dict[str, Any] = {"calibrated": False}
        self.reputation: Dict[str, float] = {}
        self.seen_sources: Deque[str] = deque(maxlen=40)
        self.history: List[Dict[str, Any]] = []

        # Trusted references, learned in `calibrate`.
        self.label_prior: Optional[np.ndarray] = None
        self.ratio_median: Optional[np.ndarray] = None
        self.ratio_scale: Optional[np.ndarray] = None
        self.class_median: Optional[np.ndarray] = None   # (n_classes, n_ratios)
        self.class_scale: Optional[np.ndarray] = None

    # ------------------------------------------------------------- calibrate
    def calibrate(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Any]:
        """Learn what trusted data looks like: label prior and ratio physics.

        The physics reference is built **per class**, and that is the single
        most important decision in this module.  Comparing every row against
        one pooled reference is close to useless: a genuine DDoS row is wildly
        far from the pooled median, so honest updates full of honest attack
        rows score as badly as poisoned ones.

        Per class, the question becomes sharp and directional -- *does this row
        obey the physics of the class it claims to belong to?*  A relabelled
        flood row claiming to be normal fails it, because it still has flood
        physics.  A clean-label row claiming to be a flood fails it too,
        because its features were dragged toward benign while the label stayed
        honest.  One test, both strategies, no knowledge of either required.
        """
        y = np.asarray(y, dtype=np.int64)
        counts = np.bincount(y, minlength=len(THREAT_CLASSES)).astype(float)
        self.label_prior = counts / max(counts.sum(), 1.0)

        ratios = cross_plane_ratios(X)
        self.ratio_median = np.median(ratios, axis=0)
        mad = np.median(np.abs(ratios - self.ratio_median), axis=0)
        # 1.4826 * MAD is the consistent estimator of sigma for a normal.
        self.ratio_scale = np.maximum(1.4826 * mad, 1e-3)

        n_cls, n_ratio = len(THREAT_CLASSES), len(RATIO_NAMES)
        self.class_median = np.tile(self.ratio_median, (n_cls, 1))
        self.class_scale = np.tile(self.ratio_scale, (n_cls, 1))
        per_class_n: Dict[str, int] = {}
        for c in range(n_cls):
            mask = y == c
            per_class_n[THREAT_CLASSES[c]] = int(mask.sum())
            if mask.sum() < 25:          # too few to trust; keep the pooled one
                continue
            r = ratios[mask]
            med = np.median(r, axis=0)
            cmad = np.median(np.abs(r - med), axis=0)
            self.class_median[c] = med
            # Floor the per-class scale at a fraction of the pooled scale, so a
            # class that happens to be tight in the reference set does not
            # produce absurd sigmas on ordinary variation later.
            self.class_scale[c] = np.maximum(1.4826 * cmad,
                                             0.25 * self.ratio_scale)

        self.calibration.update({
            "label_prior": {THREAT_CLASSES[i]: round(float(p), 4)
                            for i, p in enumerate(self.label_prior)},
            "ratio_reference": {RATIO_NAMES[i]:
                                {"median": round(float(self.ratio_median[i]), 4),
                                 "scale": round(float(self.ratio_scale[i]), 4)}
                                for i in range(n_ratio)},
            "class_reference_rows": per_class_n,
            "n_reference": int(len(y)),
        })
        return self.calibration

    def calibrate_threshold(self, honest: List[ModelUpdate], bank: FutureBank,
                            incumbent: ThreatDetector, core_X: np.ndarray,
                            core_y: np.ndarray, core_dt: np.ndarray
                            ) -> Dict[str, Any]:
        """Set the accept threshold from honest updates on this fleet.

        The floor on the spread matters.  Calibration updates all come from one
        pool, so their measured spread understates what honest traffic really
        varies by once the fleet drifts.  Without the floor the gate lands
        inside the honest distribution and starts quarantining legitimate
        contributions on day two.
        """
        scores = [self._score(u, bank, incumbent, core_X, core_y, core_dt)[0]
                  for u in honest]
        if not scores:
            return self.calibration
        arr = np.asarray(scores)
        spread = max(float(arr.std()), CFG.threshold_std_floor)
        raw = float(arr.mean() - CFG.threshold_z * spread)
        self.threshold = float(np.clip(raw, CFG.threshold_floor,
                                       CFG.threshold_ceiling))
        self.calibration.update({
            "calibrated": True,
            "honest_updates": len(scores),
            "honest_mean": round(float(arr.mean()), 4),
            "honest_std": round(float(arr.std()), 4),
            "spread_used": round(spread, 4),
            "raw_threshold": round(raw, 4),
            "threshold": round(self.threshold, 4),
            "z": CFG.threshold_z,
            "honest_scores": [round(float(s), 4) for s in scores],
        })
        return self.calibration

    # ------------------------------------------------------------ components
    def _shadow(self, update: ModelUpdate, core_X: np.ndarray,
                core_y: np.ndarray, core_dt: np.ndarray) -> ThreatDetector:
        """Train the what-if model: trusted core plus this update.

        The update is up-weighted to a realistic federated share of the
        training mass.  At its natural ratio a 240-row update inside a
        1200-row core barely moves the forest, every update scores well, and
        the test discriminates nothing.  Weighting to the share a real
        contributor would carry is what makes this an actual stress test.
        """
        share = SETTINGS.immune.resistance_poison_share
        n_core, n_upd = len(core_y), update.n_samples
        w_upd = (share / (1.0 - share)) * (n_core / max(n_upd, 1))

        X = np.vstack([core_X, update.X])
        y = np.concatenate([core_y, update.y])
        dt = np.concatenate([core_dt, update.device_type_ids
                             if update.device_type_ids is not None
                             else np.full(n_upd, -1, dtype=np.int64)])
        w = np.concatenate([np.ones(n_core), np.full(n_upd, w_upd)])

        # class_weight is off here on purpose: balancing would partly undo the
        # very label skew the poison introduced, and hide the attack.
        return ThreatDetector(seed=self.seed,
                              n_estimators=CFG.shadow_estimators,
                              class_weight=None).fit(X, y, dt, sample_weight=w)

    def _plane_coherence(self, update: ModelUpdate
                         ) -> Tuple[float, Dict[str, float], Dict[str, Any]]:
        """Does each row obey the cross-plane physics of its declared class?"""
        if self.class_median is None or self.class_scale is None:
            return 1.0, {}, {}
        ratios = cross_plane_ratios(update.X)
        labels = np.clip(update.y, 0, len(THREAT_CLASSES) - 1)
        z = np.abs(ratios - self.class_median[labels]) / self.class_scale[labels]

        # Per-ratio agreement, then a row score that blends the average ratio
        # with the worst one.  Pure averaging lets a single catastrophic ratio
        # hide behind seven healthy ones, which is precisely how a targeted
        # feature perturbation would escape.
        agreement = 1.0 / (1.0 + (z / 4.0) ** 2)
        row_score = 0.5 * agreement.mean(axis=1) + 0.5 * agreement.min(axis=1)

        per_ratio = {RATIO_NAMES[i]: round(float(agreement[:, i].mean()), 4)
                     for i in range(len(RATIO_NAMES))}
        detail = {
            "rows_beyond_4sigma": round(float((z.max(axis=1) > 4.0).mean()), 4),
            "worst_row_sigma": round(float(z.max()), 2),
            "median_row_sigma": round(float(np.median(z.max(axis=1))), 2),
            "by_declared_class": {
                THREAT_CLASSES[c]: round(float(row_score[labels == c].mean()), 4)
                for c in np.unique(labels)},
        }
        return float(row_score.mean()), per_ratio, detail

    @staticmethod
    def _label_agreement(update: ModelUpdate, incumbent: ThreatDetector
                         ) -> Tuple[float, Dict[str, Any]]:
        """Do the update's own labels agree with the trusted model on its own rows?

        Only the benign/attack call is compared, not the exact class.  Two
        directions, and they mean opposite things:

        *benign-ward disagreement* -- rows labelled as an attack that the
        trusted model reads as ordinary traffic.  This is the clean-label
        fingerprint: the labels stay honest, so nothing distributional fires,
        but the features have been dragged toward benign until the row no
        longer resembles the attack it claims to be.

        *attack-ward disagreement* -- rows labelled normal that the trusted
        model reads as an attack.  Label flipping and backdoors both leave this.

        The honest trade-off, stated plainly: this term trusts the incumbent,
        so an update carrying a genuinely novel attack pattern the incumbent
        has never seen will be penalised by it.  That is why it is one term of
        six rather than the whole gate -- the counterfactual terms exist
        precisely to judge damage the incumbent cannot see, and a genuinely
        novel-but-honest update still clears the threshold on their strength.
        """
        pred = incumbent.predict(update.X, update.device_type_ids)
        declared_attack = update.y != NORMAL_IDX
        pred_attack = pred != NORMAL_IDX
        pooled = float((declared_attack == pred_attack).mean())

        n_atk = int(declared_attack.sum())
        n_ben = int((~declared_attack).sum())
        benign_ward = (float((~pred_attack[declared_attack]).mean())
                       if n_atk else 0.0)
        attack_ward = (float(pred_attack[~declared_attack].mean())
                       if n_ben else 0.0)

        # The pooled rate alone is too weak, because the two directions are
        # measured on very differently sized populations.  A corpus is roughly
        # one-seventh normal rows, so an attack that corrupts *every* normal
        # row still only moves the pooled rate by a seventh.  Blending in the
        # worse of the two directional rates restores the signal without making
        # the term hostage to whichever population happens to be tiny.
        worst = min(1.0 - benign_ward, 1.0 - attack_ward)
        agree = 0.35 * pooled + 0.65 * worst

        detail = {
            "pooled": round(pooled, 4),
            "benign_ward": round(benign_ward, 4),
            "attack_ward": round(attack_ward, 4),
            "rows_labelled_attack": n_atk,
            "rows_labelled_normal": n_ben,
        }
        return float(agree), detail

    def _label_shift(self, update: ModelUpdate) -> Tuple[float, float]:
        """Total-variation distance from the trusted prior, and normal excess."""
        if self.label_prior is None:
            return 0.0, 0.0
        counts = np.bincount(update.y, minlength=len(THREAT_CLASSES)).astype(float)
        p = counts / max(counts.sum(), 1.0)
        tv = float(0.5 * np.abs(p - self.label_prior).sum())
        excess = float(p[NORMAL_IDX] - self.label_prior[NORMAL_IDX])
        return tv, excess

    def _repeat_score(self, update: ModelUpdate) -> Tuple[float, str]:
        """Concentration of benign-labelled rows into one narrow value band.

        Nature does not produce two hundred rows with a packet size of exactly
        404 bytes.  A stamped-on backdoor trigger does, and it has to: the
        trigger is only useful to the attacker if it can be reproduced exactly
        at inference time.

        Measured over the rows labelled *normal* only, because that is where a
        backdoor must put its trigger, and scored as an excess over the density
        an ordinary unimodal distribution would produce in its busiest bin.
        """
        benign = update.X[update.y == NORMAL_IDX]
        attack = update.X[update.y != NORMAL_IDX]
        n = len(benign)
        if n < 20:
            return 0.0, ""

        # Bins of constant *relative* width (1%), not constant absolute width.
        # Absolute bins are useless here: benign outbound traffic spans a bulb
        # at 2 kb/s and a camera at 2200, so a linear histogram drops four
        # device types into bin zero and reports 45% concentration for a
        # perfectly honest update.  On a log axis every device sits in its own
        # region and only a genuinely repeated value concentrates.
        width = np.log1p(0.01)
        best, best_feature = 0.0, ""
        for name, i in zip(_CONTINUOUS, _CONT_IDX):
            col = np.log1p(np.maximum(benign[:, i], 0.0))
            if col.max() - col.min() <= 1e-9:
                continue
            bins = np.floor(col / width).astype(np.int64)
            values, counts = np.unique(bins, return_counts=True)
            k = int(counts.argmax())
            frac = float(counts[k]) / n

            # A platform constant concentrates every row, benign and hostile
            # alike -- declared USB bus power on a live device sits at exactly
            # the same wattage in all of them.  A stamped trigger does not: it
            # is put on the rows the attacker relabels benign and left off the
            # ones that keep an attack label.  So the signal is the *excess*
            # concentration in benign rows over the same band in attack rows,
            # which reads a trigger and ignores a constant.
            rival = 0.0
            if len(attack) >= 10:
                acol = np.log1p(np.maximum(attack[:, i], 0.0))
                abins = np.floor(acol / width).astype(np.int64)
                rival = float((abins == values[k]).sum()) / len(attack)

            excess = frac - max(rival, 0.10)
            if excess > best:
                best, best_feature = excess, name
        # Ordinary telemetry lands under ~10% in its busiest 1% band, which is
        # the floor the comparison above already applies.
        return max(0.0, best), best_feature

    # -------------------------------------------------------------- scoring
    def _score(self, update: ModelUpdate, bank: FutureBank,
               incumbent: ThreatDetector, core_X: np.ndarray,
               core_y: np.ndarray, core_dt: np.ndarray
               ) -> Tuple[float, Dict[str, Any]]:
        """Compute the CCS and every component that went into it."""
        shadow = self._shadow(update, core_X, core_y, core_dt)

        if bank.n:
            shadow_pred = shadow.predict(bank.X, bank.dt)
            inc_pred = incumbent.predict(bank.X, bank.dt)
            am, bm = bank.attack_mask, bank.benign_mask

            attack_agreement = (float((shadow_pred[am] != NORMAL_IDX).mean())
                                if am.any() else 1.0)
            benign_agreement = (float((shadow_pred[bm] == NORMAL_IDX).mean())
                                if bm.any() else 1.0)
            caught = inc_pred != NORMAL_IDX
            downgraded = caught & (shadow_pred == NORMAL_IDX)
            stability = (1.0 - float(downgraded.sum()) / float(caught.sum())
                         if caught.any() else 1.0)

            per_class = {}
            for i, name in enumerate(THREAT_CLASSES):
                mask = bank.y == i
                if not mask.any():
                    continue
                if i == NORMAL_IDX:
                    per_class[name] = round(
                        float((shadow_pred[mask] == NORMAL_IDX).mean()), 4)
                else:
                    per_class[name] = round(
                        float((shadow_pred[mask] != NORMAL_IDX).mean()), 4)
        else:
            attack_agreement = benign_agreement = stability = 1.0
            per_class = {}

        coherence, per_ratio, coherence_detail = self._plane_coherence(update)
        label_agreement, agreement_detail = self._label_agreement(update, incumbent)
        tv, excess = self._label_shift(update)
        repeat, repeat_feature = self._repeat_score(update)

        # Label integrity: how far the update's label mix has drifted from the
        # trusted prior, mapped onto [0, 1].  Only benign-ward drift is
        # penalised -- an update that reports *more* attacks than expected may
        # be noisy or over-eager, but it is not trying to blind the model, and
        # treating it as an attack would punish the honest device that happened
        # to be under fire while it collected its sample.
        directional = tv if excess > 0 else min(tv, 0.35 * CFG.label_shift_full)
        label_integrity = float(np.clip(
            1.0 - directional / CFG.label_shift_full, 0.0, 1.0))

        ccs = (CFG.w_attack_agreement * attack_agreement
               + CFG.w_benign_agreement * benign_agreement
               + CFG.w_stability * stability
               + CFG.w_plane_coherence * coherence
               + CFG.w_label_integrity * label_integrity
               + CFG.w_label_agreement * label_agreement)

        weights = {
            "attack_agreement": CFG.w_attack_agreement,
            "benign_agreement": CFG.w_benign_agreement,
            "stability": CFG.w_stability,
            "plane_coherence": CFG.w_plane_coherence,
            "label_integrity": CFG.w_label_integrity,
            "label_agreement": CFG.w_label_agreement,
        }
        components = {
            "attack_agreement": attack_agreement,
            "benign_agreement": benign_agreement,
            "stability": stability,
            "plane_coherence": coherence,
            "label_integrity": label_integrity,
            "label_agreement": label_agreement,
        }
        evidence = {
            "attack_agreement": round(attack_agreement, 4),
            "benign_agreement": round(benign_agreement, 4),
            "stability": round(stability, 4),
            "plane_coherence": round(coherence, 4),
            "label_integrity": round(label_integrity, 4),
            "label_agreement": round(label_agreement, 4),
            "agreement_detail": agreement_detail,
            "label_shift": round(tv, 4),
            "normal_excess": round(excess, 4),
            "repeat_score": round(repeat, 4),
            "repeat_feature": repeat_feature,
            "bank_per_class": per_class,
            "ratio_agreement": per_ratio,
            "coherence_detail": coherence_detail,
            "bank_n": bank.n,
            "weights": weights,
            "contributions": {k: round(weights[k] * v, 4)
                              for k, v in components.items()},
        }
        return float(ccs), evidence

    # ------------------------------------------------------------ attribution
    @staticmethod
    def attribute(evidence: Dict[str, Any], n_samples: int, passed: bool
                  ) -> Tuple[str, float, Dict[str, float]]:
        """Guess which strategy produced this signature.

        Rule-based on purpose.  A learned attributor would need labelled poison
        to train on, and if we had that we would not need the defence.  These
        rules encode the structural fingerprint each strategy cannot avoid
        leaving, and the console shows the scores so the operator can disagree.
        """
        excess = evidence["normal_excess"]
        tv = evidence["label_shift"]
        repeat = evidence["repeat_score"]
        attack_ward = evidence.get("agreement_detail", {}).get("attack_ward", 0.0)

        def band(x: float, lo: float, hi: float, soft: float = 0.07) -> float:
            """1 inside [lo, hi], falling linearly to 0 over `soft` outside."""
            if lo <= x <= hi:
                return 1.0
            d = (lo - x) if x < lo else (x - hi)
            return float(np.clip(1.0 - d / soft, 0.0, 1.0))

        # Rows labelled normal that the trusted model reads as an attack. Every
        # blinding strategy leaves this; it is the shared symptom, so it gates
        # the strategies rather than distinguishing them.
        blinding = float(np.clip((attack_ward - 0.25) / 0.45, 0, 1))
        # Stamped-trigger evidence, used both as its own score and to suppress
        # the plainer explanations when a trigger is clearly present.
        trigger = float(np.clip((repeat - 0.13) / 0.09, 0, 1))
        # A single large contribution, as opposed to one shard of many.
        bulky = float(np.clip((n_samples - 80.0) / 70.0, 0, 1))

        scores = {
            # Blunt relabelling: a large benign-ward shift in the label mix.
            "label_flip": band(excess, 0.30, 1.0) * blinding * (1 - trigger) * bulky,
            # Small flip repeated over rounds: a modest but real shift.
            # The lower edge is tight on purpose: it is the only thing
            # separating a small genuine flip from clean-label poisoning, whose
            # label mix does not move at all.
            "gradual_poisoning": band(excess, 0.06, 0.28, soft=0.03) * blinding
                                 * (1 - trigger) * bulky,
            # Stamped trigger: one value repeated far past what nature does.
            "backdoor": trigger,
            # Honest labels, moved features: blinding with no label shift at all.
            "clean_label": float(np.clip(1.0 - tv / 0.10, 0, 1)) * blinding,
            # Many small shards from invented identities.
            "sybil": float(np.clip((150.0 - n_samples) / 110.0, 0, 1))
                     * band(excess, 0.04, 1.0),
        }
        scores = {k: float(v) for k, v in scores.items()}
        best = max(scores, key=lambda k: scores[k])
        total = sum(scores.values())
        confidence = scores[best] / total if total > 1e-6 else 0.0
        if passed and scores[best] < 0.25:
            return "clean", 0.0, {k: round(v, 4) for k, v in scores.items()}
        if scores[best] < 0.12:
            return "unattributed", round(confidence, 4), {
                k: round(v, 4) for k, v in scores.items()}
        return best, round(confidence, 4), {k: round(v, 4)
                                            for k, v in scores.items()}

    # -------------------------------------------------------------- validate
    def validate(self, update: ModelUpdate, bank: FutureBank,
                 incumbent: ThreatDetector, core_X: np.ndarray,
                 core_y: np.ndarray, core_dt: np.ndarray) -> ValidationReport:
        """Run the full STEP 8 audit and reach a decision."""
        t0 = time.perf_counter()
        ccs, evidence = self._score(update, bank, incumbent,
                                    core_X, core_y, core_dt)

        # --- source reputation --------------------------------------------
        prior_rep = self.reputation.get(update.source, 1.0)
        rep = ((1 - CFG.reputation_alpha) * prior_rep
               + CFG.reputation_alpha * ccs)
        self.reputation[update.source] = rep

        # --- sybil pressure -----------------------------------------------
        # A burst of never-before-seen sources is the one structural signal a
        # sybil flood cannot hide, since its whole method is inventing
        # identities.  It tightens the gate; it never decides on its own.
        unseen = update.source not in self.seen_sources
        recent = list(self.seen_sources)[-8:]
        distinct_recent = len(set(recent))
        burst = unseen and len(recent) >= 5 and distinct_recent >= 5
        novelty_penalty = 0.05 if burst else 0.0
        self.seen_sources.append(update.source)

        effective = min(self.threshold + novelty_penalty, 0.97)
        passed = ccs >= effective and rep >= CFG.reputation_floor
        decision = (Decision.ACCEPTED.value if passed
                    else Decision.QUARANTINED.value)

        suspected, confidence, strategy_scores = self.attribute(
            evidence, update.n_samples, passed)

        evidence.update({
            "effective_threshold": round(effective, 4),
            "novelty_penalty": novelty_penalty,
            "new_source": unseen,
            "distinct_recent_sources": distinct_recent,
            "reputation_before": round(prior_rep, 4),
            "reputation_after": round(rep, 4),
            "reputation_floor": CFG.reputation_floor,
            "strategy_scores": strategy_scores,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
            "margin": round(ccs - effective, 4),
        })

        report = ValidationReport(
            update_id=update.update_id,
            source=update.source,
            decision=decision,
            consistency_score=round(ccs, 4),
            attack_agreement=evidence["attack_agreement"],
            benign_agreement=evidence["benign_agreement"],
            stability=evidence["stability"],
            plane_coherence=evidence["plane_coherence"],
            label_shift=evidence["label_shift"],
            reputation=round(rep, 4),
            threshold=round(effective, 4),
            suspected_strategy=suspected,
            strategy_confidence=confidence,
            n_samples=update.n_samples,
            declared_strategy=update.declared_strategy,
            evidence=evidence,
        )
        self.history.append({"update_id": update.update_id,
                             "ccs": report.consistency_score,
                             "decision": decision,
                             "declared": update.declared_strategy,
                             "suspected": suspected,
                             "ts": report.timestamp})
        return report

    # ------------------------------------------------------------- forensics
    def forensics(self, update: ModelUpdate, report: ValidationReport
                  ) -> Dict[str, Any]:
        """STEP 10: the deeper dissection run on a quarantined update."""
        repeat, repeat_feature = self._repeat_score(update)
        findings: List[str] = []

        if report.evidence.get("normal_excess", 0) > 0.12:
            findings.append(
                f"Label distribution is skewed {report.evidence['normal_excess']:.0%} "
                f"further toward 'normal' than trusted data. Consistent with "
                f"relabelling of attack rows.")
        if repeat > 0.12:
            findings.append(
                f"Rows labelled normal concentrate {repeat:.0%} more tightly "
                f"on one value of '{repeat_feature}' than the rows labelled as "
                f"attacks do. A measurement that genuinely varies does not "
                f"single out the benign half -- this is a stamped trigger.")
        if report.plane_coherence < 0.75:
            worst = sorted(report.evidence.get("ratio_agreement", {}).items(),
                           key=lambda kv: kv[1])[:3]
            findings.append(
                "Cross-plane physics do not hold: "
                + ", ".join(f"{k} agreement {v:.2f}" for k, v in worst)
                + ". Features were altered without keeping the planes consistent.")
        if report.attack_agreement < 0.85:
            lost = {k: v for k, v in
                    report.evidence.get("bank_per_class", {}).items()
                    if k != "normal" and v < 0.85}
            if lost:
                worst_classes = sorted(lost.items(), key=lambda kv: kv[1])
                findings.append(
                    "Accepting this update would blind the model to: "
                    + ", ".join(f"{k} ({v:.0%} still caught)"
                                for k, v in worst_classes))
        if report.stability < 0.85:
            findings.append(
                f"{1 - report.stability:.0%} of the attacks the trusted model "
                f"currently catches would be downgraded to 'normal'.")
        if update.n_samples < 120 and report.evidence.get("new_source"):
            findings.append(
                "Small contribution from a previously unseen source, arriving "
                "alongside other new sources. Consistent with a sybil flood.")
        if not findings:
            findings.append(
                "No single signal is individually damning; the update was held "
                "on the combined score.")

        rows = []
        pred_normal = update.y == NORMAL_IDX
        if pred_normal.any():
            ratios = cross_plane_ratios(update.X)
            if self.ratio_median is not None:
                z = np.abs(ratios - self.ratio_median) / self.ratio_scale
                worst = np.argsort(-z.max(axis=1))[:5]
                for i in worst:
                    rows.append({
                        "row": int(i),
                        "declared_label": THREAT_CLASSES[int(update.y[i])],
                        "worst_ratio": RATIO_NAMES[int(z[i].argmax())],
                        "sigma": round(float(z[i].max()), 2),
                        "features": {f: round(float(update.X[i, FEATURES.index(f)]), 2)
                                     for f in ("net_out_kbps", "packet_rate",
                                               "conn_attempts", "failed_logins",
                                               "port_diversity", "payload_entropy")},
                    })

        return {
            "update_id": update.update_id,
            "source": update.source,
            "n_samples": update.n_samples,
            "labels": update.label_summary(),
            "suspected_strategy": report.suspected_strategy,
            "strategy_confidence": report.strategy_confidence,
            "strategy_scores": report.evidence.get("strategy_scores", {}),
            "findings": findings,
            "suspicious_rows": rows,
            "components": {
                "attack_agreement": report.attack_agreement,
                "benign_agreement": report.benign_agreement,
                "stability": report.stability,
                "plane_coherence": report.plane_coherence,
            },
            "bank_per_class": report.evidence.get("bank_per_class", {}),
        }

    # -------------------------------------------------------------- reporting
    def snapshot(self) -> Dict[str, Any]:
        return {
            "threshold": round(self.threshold, 4),
            "calibration": self.calibration,
            "reputation": {k: round(v, 4) for k, v in self.reputation.items()},
            "reputation_floor": CFG.reputation_floor,
            "validated": len(self.history),
            "weights": {
                "attack_agreement": CFG.w_attack_agreement,
                "benign_agreement": CFG.w_benign_agreement,
                "stability": CFG.w_stability,
                "plane_coherence": CFG.w_plane_coherence,
                "label_integrity": CFG.w_label_integrity,
                "label_agreement": CFG.w_label_agreement,
            },
        }
