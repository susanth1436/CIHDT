"""Detection, counterfactual validation, immunization, retraining, healing.

These are the tests that decide whether the framework's central claim holds:
honest contributions are accepted, and every poisoning strategy is caught.
"""
from __future__ import annotations

import numpy as np
import pytest

from cihdt.config import SETTINGS
from cihdt.counterfactual.bank import build_bank
from cihdt.counterfactual.validator import CounterfactualValidator
from cihdt.detection.features import cross_plane_ratios, engineer
from cihdt.detection.model import ThreatDetector
from cihdt.immunization.engine import ImmunizationEngine
from cihdt.poisoning.attacks import PoisonForge
from cihdt.quarantine.store import QuarantineZone
from cihdt.retraining.registry import ModelRegistry
from cihdt.retraining.retrainer import SecureRetrainer
from cihdt.schemas import ATTACK_STRATEGIES, NORMAL_IDX, THREAT_CLASSES
from cihdt.selfheal.monitor import SelfHealingMonitor
from cihdt.simulator.fleet import IoTFleet, build_corpus
from cihdt.twin.registry import TwinRegistry

MIXED = [("smart_camera", 2), ("smart_bulb", 2), ("smart_plug", 1),
         ("smart_lock", 1), ("temperature_sensor", 1), ("smart_speaker", 1)]


@pytest.fixture(scope="module")
def rig():
    """A trained, armed, calibrated system -- built once for the module."""
    fleet = IoTFleet(seed=11)
    for dtype, count in MIXED:
        for _ in range(count):
            fleet.add_device(dtype)

    twins = TwinRegistry(seed=11)
    for dev in fleet.devices.values():
        twins.create(dev.device_id, dev.device_type)
    for _ in range(55):
        twins.observe_batch(fleet.tick())
    twins.arm_all()

    X, y, dt = build_corpus(fleet.layout, rows_per_class=380, seed=13)
    cut = int(0.65 * len(y))
    detector = ThreatDetector(seed=11).fit(X[:cut], y[:cut], dt[:cut])
    bank = build_bank(twins, trusted_detector=detector, seed=11)

    rng = np.random.default_rng(5)
    core_idx = rng.choice(cut, 1100, replace=False)
    core = (X[core_idx], y[core_idx], dt[core_idx])
    pool = (X[cut:], y[cut:], dt[cut:])

    validator = CounterfactualValidator(seed=11)
    validator.calibrate(X[:cut], y[:cut])
    forge = PoisonForge(seed=11)
    honest = [forge.clean_update(*pool, source=f"calib_{i:02d}", n=240)
              for i in range(8)]
    validator.calibrate_threshold(honest, bank, detector, *core)

    return {"fleet": fleet, "twins": twins, "detector": detector, "bank": bank,
            "core": core, "pool": pool, "validator": validator, "forge": forge,
            "train": (X[:cut], y[:cut], dt[:cut]),
            "eval": (X[cut:], y[cut:], dt[cut:])}


# ---------------------------------------------------------------- STEP 6 ----
def test_engineered_features_are_finite_and_wider_than_raw():
    X, y, dt = build_corpus([("smart_camera", 1), ("smart_bulb", 1)],
                            rows_per_class=40, seed=2)
    Xe = engineer(X, dt)
    assert Xe.shape[0] == X.shape[0]
    assert Xe.shape[1] > X.shape[1]
    assert np.isfinite(Xe).all()


def test_cross_plane_ratios_detect_physical_inconsistency():
    """Throughput that rate and packet size cannot account for must stand out."""
    X, y, dt = build_corpus([("smart_camera", 1)], rows_per_class=40, seed=2)
    honest = cross_plane_ratios(X)
    tampered = X.copy()
    from cihdt.schemas import FEATURE_INDEX
    tampered[:, FEATURE_INDEX["net_out_kbps"]] *= 500      # volume only
    faked = cross_plane_ratios(tampered)
    col = 2                                                # r_volume_coherence
    assert abs(faked[:, col].mean()) > abs(honest[:, col].mean()) + 1.0


def test_detector_separates_normal_from_attack(rig):
    metrics = rig["detector"].evaluate(*rig["eval"])
    assert metrics["accuracy"] > 0.88
    assert metrics["false_negative_rate"] < 0.12
    assert metrics["false_positive_rate"] < 0.15


def test_probabilities_span_the_full_taxonomy(rig):
    X, _y, dt = rig["eval"]
    probs = rig["detector"].predict_proba(X[:20], dt[:20])
    assert probs.shape == (20, len(THREAT_CLASSES))
    assert np.allclose(probs.sum(axis=1), 1.0, atol=1e-6)


# ---------------------------------------------------------------- STEP 5 ----
def test_bank_holds_both_populations_and_the_incumbent_gets_them_right(rig):
    bank = rig["bank"]
    assert bank.n > 100
    assert bank.attack_mask.sum() > 0 and bank.benign_mask.sum() > 0
    pred = rig["detector"].predict(bank.X, bank.dt)
    correct = ((bank.y == NORMAL_IDX) == (pred == NORMAL_IDX))
    # Filtering at build time means the trusted model starts from a clean slate.
    assert correct.mean() > 0.99


# ---------------------------------------------------------------- STEP 8 ----
def test_honest_updates_are_accepted(rig):
    v, forge = rig["validator"], rig["forge"]
    decisions = []
    for i in range(4):
        u = forge.clean_update(*rig["pool"], source="honest_hub", n=240)
        r = v.validate(u, rig["bank"], rig["detector"], *rig["core"])
        decisions.append(r.decision)
    assert decisions == ["ACCEPTED"] * 4


@pytest.mark.parametrize("strategy", ATTACK_STRATEGIES)
def test_every_poisoning_strategy_is_quarantined(strategy, rig):
    v, forge = rig["validator"], rig["forge"]
    updates = forge.craft(strategy, *rig["pool"], source=f"bad_{strategy}",
                          n=240, potency=1.0)
    reports = [v.validate(u, rig["bank"], rig["detector"], *rig["core"])
               for u in updates]
    assert all(r.decision == "QUARANTINED" for r in reports), \
        f"{strategy} slipped through: {[r.consistency_score for r in reports]}"


def test_poison_scores_below_honest_by_a_clear_margin(rig):
    v, forge = rig["validator"], rig["forge"]
    honest = [v.validate(forge.clean_update(*rig["pool"], source="h", n=240),
                         rig["bank"], rig["detector"], *rig["core"]
                         ).consistency_score for _ in range(3)]
    poisoned = []
    for strategy in ATTACK_STRATEGIES:
        for u in forge.craft(strategy, *rig["pool"], source="p", n=240):
            poisoned.append(v.validate(u, rig["bank"], rig["detector"],
                                       *rig["core"]).consistency_score)
    assert min(honest) - max(poisoned) > 0.05


def test_clean_label_is_caught_by_label_agreement(rig):
    """Its labels are honest, so only the incumbent cross-check can see it."""
    v, forge = rig["validator"], rig["forge"]
    u = forge.craft("clean_label", *rig["pool"], source="cl", n=240)[0]
    r = v.validate(u, rig["bank"], rig["detector"], *rig["core"])
    assert r.label_shift < 0.10               # distributionally invisible
    assert r.evidence["label_agreement"] < 0.6
    assert r.decision == "QUARANTINED"


def test_validator_never_reads_the_declared_strategy(rig):
    """The ground-truth tag must not influence the score."""
    v, forge = rig["validator"], rig["forge"]
    u = forge.craft("label_flip", *rig["pool"], source="x", n=240)[0]
    honest_score = v.validate(u, rig["bank"], rig["detector"],
                              *rig["core"]).consistency_score
    u.declared_strategy = "clean"             # lie about it
    lying_score = v.validate(u, rig["bank"], rig["detector"],
                             *rig["core"]).consistency_score
    assert abs(honest_score - lying_score) < 1e-9


def test_threshold_is_calibrated_not_hardcoded(rig):
    cal = rig["validator"].calibration
    assert cal["calibrated"] is True
    assert cal["threshold"] < cal["honest_mean"]
    assert SETTINGS.validate.threshold_floor <= cal["threshold"] \
        <= SETTINGS.validate.threshold_ceiling


def test_forensics_explains_a_quarantine(rig):
    v, forge = rig["validator"], rig["forge"]
    u = forge.craft("backdoor", *rig["pool"], source="bd", n=240)[0]
    r = v.validate(u, rig["bank"], rig["detector"], *rig["core"])
    report = v.forensics(u, r)
    assert report["findings"]
    assert all(isinstance(f, str) and f for f in report["findings"])


# ---------------------------------------------------------------- STEP 9 ----
def test_vaccines_are_labelled_as_attacks_and_physically_valid(rig):
    engine = ImmunizationEngine(seed=3)
    X, y, dt, w, report = engine.synthesize(rig["bank"])
    assert report["rows"] > 0
    assert len(y) == len(X) == len(w)
    assert (y != NORMAL_IDX).all()     # a vaccine never teaches "attack = normal"
    assert np.isfinite(X).all()
    assert (X >= 0).all()


def test_poison_resistance_is_measured_per_strategy(rig):
    engine = ImmunizationEngine(seed=3)
    X, y, dt = rig["train"]
    result = engine.poison_resistance(X[:900], y[:900], dt[:900], rig["bank"])
    assert set(result["per_strategy"]) == set(ATTACK_STRATEGIES)
    assert 0.0 <= result["poison_resistance"] <= 1.0
    assert result["weakest"] in ATTACK_STRATEGIES


# --------------------------------------------------------------- STEP 10 ----
def test_quarantine_holds_without_destroying(rig):
    v, forge = rig["validator"], rig["forge"]
    zone = QuarantineZone()
    u = forge.craft("label_flip", *rig["pool"], source="q", n=240)[0]
    r = v.validate(u, rig["bank"], rig["detector"], *rig["core"])
    zone.add(u, r)
    assert len(zone.held()) == 1
    assert zone.get(u.update_id).update.n_samples == 240   # intact
    zone.release(u.update_id, reason="test")
    assert len(zone.held()) == 0
    assert zone.total_released == 1


# --------------------------------------------------------------- STEP 11 ----
def test_promotion_gates_reject_a_degraded_candidate(rig, tmp_path):
    """A pool of pure poison must not be promoted, however it scores."""
    registry = ModelRegistry(root=tmp_path / "models", reset=True)
    immunizer = ImmunizationEngine(seed=3)
    retrainer = SecureRetrainer(registry, immunizer, seed=3)

    X, y, dt = rig["train"]
    retrainer.seed_pool(X[:400], y[:400], dt[:400])
    # Everything relabelled benign: accuracy must collapse.
    retrainer.y[:] = NORMAL_IDX

    outcome = retrainer.retrain(rig["bank"], *rig["eval"],
                                incumbent=rig["detector"], immunize=False,
                                measure_resistance=False)
    assert not outcome.promoted
    assert not outcome.gates["accuracy"]["pass"]


def test_pool_provenance_allows_surgical_purge(rig, tmp_path):
    registry = ModelRegistry(root=tmp_path / "models", reset=True)
    retrainer = SecureRetrainer(registry, ImmunizationEngine(seed=3), seed=3)
    X, y, dt = rig["train"]
    retrainer.seed_pool(X[:300], y[:300], dt[:300])

    forge = PoisonForge(seed=9)
    bad = forge.craft("label_flip", *rig["pool"], source="hostile", n=200)[0]
    retrainer.accept(bad)
    assert retrainer.pool_size == 500

    event = retrainer.purge(sources=["hostile"], reason="test")
    assert event["removed_rows"] == 200
    assert retrainer.pool_size == 300          # trusted rows untouched


# --------------------------------------------------------------- STEP 12 ----
def test_registry_rolls_back_to_the_last_trusted_version(rig, tmp_path):
    registry = ModelRegistry(root=tmp_path / "models", reset=True)
    metrics = {"accuracy": 0.95, "macro_f1": 0.95, "false_positive_rate": 0.03,
               "false_negative_rate": 0.03, "n_train": 100}
    v1 = registry.register(rig["detector"], metrics, 0.9, notes="first")
    v2 = registry.register(rig["detector"], metrics, 0.9, notes="second")
    assert registry.active_version == v2.version

    target = registry.last_trusted_before(v2.version)
    assert target.version == v1.version
    registry.distrust(v2.version, reason="compromised")
    registry.activate(target.version)
    assert registry.active_version == v1.version
    assert registry.get(v2.version).trusted is False
    assert registry.load(v1.version) is not None


def test_health_monitor_needs_evidence_before_judging():
    monitor = SelfHealingMonitor()
    check = monitor.check()
    assert check.evaluated is False
    assert "twin flags" in check.note


def test_health_monitor_spots_a_blinded_model():
    """Twin keeps flagging, model keeps saying normal: that is the signature."""
    from cihdt.schemas import ThreatVerdict

    monitor = SelfHealingMonitor()

    def feed(n, twin_flag, model_class):
        for _ in range(n):
            monitor.record(ThreatVerdict(
                device_id="d", predicted_class=model_class, confidence=0.9,
                risk_level="NONE", twin_flagged=twin_flag), twin_ready=True)

    # Healthy: the two detectors agree. Establish the baseline.
    for _ in range(SETTINGS.heal.baseline_checks):
        feed(30, True, "ddos")
        monitor.check()
    assert monitor.baseline is not None and monitor.baseline > 0.9

    # Poisoned: the twin still flags, the model has gone quiet.
    feed(60, True, "normal")
    check = monitor.check()
    assert check.evaluated and check.degraded
    assert check.agreement < 0.2
    assert check.reasons
