"""Simulator and holographic twin behaviour (STEPS 1, 3, 4, 5)."""
from __future__ import annotations

import numpy as np
import pytest

from cihdt.config import SETTINGS
from cihdt.schemas import ATTACK_CLASSES, FEATURES, N_FEATURES, THREAT_CLASSES
from cihdt.simulator.fleet import IoTFleet, build_corpus
from cihdt.twin.registry import TwinRegistry

MIXED = [("smart_camera", 2), ("smart_bulb", 2), ("smart_plug", 1),
         ("smart_lock", 1), ("temperature_sensor", 1), ("smart_speaker", 1)]


def make_fleet(seed: int = 7) -> IoTFleet:
    fleet = IoTFleet(seed=seed)
    for dtype, count in MIXED:
        for _ in range(count):
            fleet.add_device(dtype)
    return fleet


def warm(fleet: IoTFleet, ticks: int = 55, seed: int = 7) -> TwinRegistry:
    twins = TwinRegistry(seed=seed)
    for dev in fleet.devices.values():
        twins.create(dev.device_id, dev.device_type)
    for _ in range(ticks):
        twins.observe_batch(fleet.tick())
    return twins


# --------------------------------------------------------------- STEP 1 ----
def test_devices_get_distinct_ids_and_layout():
    fleet = make_fleet()
    assert len(fleet) == 8
    assert len(set(fleet.devices)) == 8
    assert dict(fleet.layout)["smart_camera"] == 2


def test_telemetry_is_bounded_and_shaped():
    fleet = make_fleet()
    for batch in fleet.collect(5):
        for rec in batch:
            assert rec.values.shape == (N_FEATURES,)
            assert np.isfinite(rec.values).all()
            assert (rec.values >= 0).all()
            assert rec.values[FEATURES.index("cpu_usage")] <= 100.0


def test_device_types_are_actually_different():
    """A bulb and a camera must not look alike, or the model learns nothing."""
    fleet = make_fleet()
    fleet.collect(20)
    out = FEATURES.index("net_out_kbps")
    cam = fleet.get("smart_camera_01").last.values[out]
    bulb = fleet.get("smart_bulb_01").last.values[out]
    assert cam > bulb * 50


@pytest.mark.parametrize("attack", ATTACK_CLASSES)
def test_every_attack_visibly_deforms_telemetry(attack):
    fleet = make_fleet()
    fleet.collect(10)
    dev = fleet.get("smart_camera_01")
    before = dev.last.values.copy()
    dev.start_attack(attack, duration=6, intensity=1.0)
    for _ in range(3):
        fleet.tick()
    after = dev.last.values
    assert dev.ground_truth == attack
    # At least one feature must move by more than half an order of magnitude.
    ratio = (after + 1e-6) / (before + 1e-6)
    assert ratio.max() > 1.6 or ratio.min() < 0.6


def test_attacks_expire_on_their_own():
    fleet = make_fleet()
    dev = fleet.get("smart_lock_01")
    dev.start_attack("brute_force", duration=3, intensity=1.0)
    for _ in range(5):
        fleet.tick()
    assert not dev.is_compromised
    assert dev.ground_truth == "normal"


def test_corpus_covers_every_class():
    fleet = make_fleet()
    X, y, dt = build_corpus(fleet.layout, rows_per_class=60, seed=3)
    assert X.shape == (len(y), N_FEATURES)
    counts = np.bincount(y, minlength=len(THREAT_CLASSES))
    assert (counts == 60).all()
    assert np.isfinite(X).all()


# ------------------------------------------------------------ STEPS 3-5 ----
def test_twin_becomes_ready_only_after_enough_history():
    fleet = make_fleet()
    twins = TwinRegistry(seed=1)
    for dev in fleet.devices.values():
        twins.create(dev.device_id, dev.device_type)
    for _ in range(SETTINGS.twin.min_fit - 5):
        twins.observe_batch(fleet.tick())
    assert twins.ready_count == 0
    for _ in range(10):
        twins.observe_batch(fleet.tick())
    assert twins.ready_count == len(fleet)


def test_predictor_forecasts_near_the_current_level():
    fleet = make_fleet()
    twins = warm(fleet)
    twin = twins.get("smart_camera_01")
    assert twin.fit()
    predicted = twin.predictor.predict_next(twin.matrix())
    current = twin.matrix()[-1]
    i = FEATURES.index("net_out_kbps")
    # A one-step forecast of a stationary device should be the right order.
    assert 0.3 * current[i] < predicted[i] < 3.0 * current[i]


def test_futures_are_committed_before_scoring():
    fleet = make_fleet()
    twins = warm(fleet)
    twins.arm_all()
    twin = twins.get("smart_camera_01")
    assert twin.has_futures
    assert twin.futures.shape == (SETTINGS.twin.n_futures,
                                  SETTINGS.twin.horizon, N_FEATURES)
    committed_at = twin.futures_at_observation
    twins.score_batch(fleet.tick())
    # Scoring must not silently regenerate the commitment it is judging against.
    assert twin.futures_at_observation == committed_at


def test_normal_traffic_is_not_flagged_but_attacks_are():
    """The separation the whole framework depends on."""
    fleet = make_fleet()
    twins = warm(fleet, ticks=60)
    threshold = SETTINGS.validate.obs_anomaly_threshold

    normal = []
    for _ in range(10):
        twins.arm_all()
        for _rec, cf in twins.score_batch(fleet.tick()):
            normal.append(cf["consistency"])
        twins.observe_batch(fleet.tick())

    attacked = []
    for attack in ATTACK_CLASSES:
        twins.arm_all()
        for dev in fleet.devices.values():
            dev.start_attack(attack, duration=4, intensity=1.0)
        for _rec, cf in twins.score_batch(fleet.tick()):
            attacked.append(cf["consistency"])
        for dev in fleet.devices.values():
            dev.stop_attack()

    normal, attacked = np.array(normal), np.array(attacked)
    # No false alarms on healthy traffic, and most attacks caught.
    assert (normal < threshold).mean() <= 0.02
    assert (attacked < threshold).mean() >= 0.80
    assert normal.mean() > attacked.mean() * 3


def test_trust_gate_keeps_hostile_data_out_of_the_twin():
    """An attacker who can teach the twin that an attack is normal has won."""
    fleet = make_fleet()
    twins = warm(fleet)
    twin = twins.get("smart_camera_01")
    before = len(twin.history)

    twins.arm_all()
    fleet.get("smart_camera_01").start_attack("ddos", duration=4, intensity=1.0)
    for rec, cf in twins.score_batch(fleet.tick()):
        flagged = cf["ready"] and cf["consistency"] < SETTINGS.validate.obs_anomaly_threshold
        twins.twins[rec.device_id].observe(rec, trusted=not flagged)

    assert len(twin.history) == before      # refused
    assert twin.rejected >= 1


def test_plane_deviation_localises_the_attack():
    """A port scan should light up topology, not resources."""
    fleet = make_fleet()
    twins = warm(fleet)
    twins.arm_all()
    fleet.get("temperature_sensor_01").start_attack("port_scan", 4, 1.0)
    scored = {rec.device_id: cf for rec, cf in twins.score_batch(fleet.tick())}
    cf = scored["temperature_sensor_01"]
    assert "topology" in cf["anomalous_planes"]
    assert cf["plane_deviation"]["topology"] > cf["plane_deviation"]["resource"]
