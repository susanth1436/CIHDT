"""Shared vocabulary: the feature space, the holographic planes, the threat
taxonomy, and the records the twelve steps hand to one another.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# STEP 1 feature space.  One flat, device-agnostic vector, so a single edge
# model can reason across heterogeneous consumer hardware.
# ---------------------------------------------------------------------------
FEATURES: List[str] = [
    "cpu_usage",          # percent
    "mem_usage",          # percent
    "net_in_kbps",
    "net_out_kbps",
    "packet_rate",        # packets / sec
    "conn_attempts",      # per tick
    "failed_logins",      # per tick
    "unique_dst_ips",
    "port_diversity",     # distinct destination ports touched
    "cmd_rate",           # control-plane commands per tick
    "payload_entropy",    # bits / byte, 0..8
    "avg_pkt_size",       # bytes
    "session_duration",   # seconds
    "reconnects",
    "device_event_rate",  # motion events / lock actuations / toggles
    "power_draw",         # watts
]
N_FEATURES = len(FEATURES)
FEATURE_INDEX: Dict[str, int] = {f: i for i, f in enumerate(FEATURES)}

FEATURE_UNITS: Dict[str, str] = {
    "cpu_usage": "%", "mem_usage": "%", "net_in_kbps": "kb/s",
    "net_out_kbps": "kb/s", "packet_rate": "pkt/s", "conn_attempts": "/tick",
    "failed_logins": "/tick", "unique_dst_ips": "hosts",
    "port_diversity": "ports", "cmd_rate": "/tick",
    "payload_entropy": "bits/B", "avg_pkt_size": "B",
    "session_duration": "s", "reconnects": "/tick",
    "device_event_rate": "/tick", "power_draw": "W",
}

# Physically meaningful limits; simulated and synthetic data are clamped here.
FEATURE_BOUNDS: Dict[str, tuple] = {
    "cpu_usage": (0.0, 100.0),
    "mem_usage": (0.0, 100.0),
    "net_in_kbps": (0.0, 1_000_000.0),
    "net_out_kbps": (0.0, 1_000_000.0),
    "packet_rate": (0.0, 400_000.0),
    "conn_attempts": (0.0, 5_000.0),
    "failed_logins": (0.0, 5_000.0),
    "unique_dst_ips": (0.0, 4_000.0),
    "port_diversity": (0.0, 65_535.0),
    "cmd_rate": (0.0, 2_000.0),
    "payload_entropy": (0.0, 8.0),
    "avg_pkt_size": (20.0, 9_000.0),
    "session_duration": (0.0, 86_400.0),
    "reconnects": (0.0, 500.0),
    "device_event_rate": (0.0, 1_000.0),
    "power_draw": (0.0, 3_000.0),
}

# Smallest deviation that is physically meaningful for each feature.  Counts
# are integers, so a jump from 1 destination host to 2 is a single quantum of
# change, not a fifty-sigma event -- without this floor a twin watching an idle
# temperature sensor flags every ordinary tick, because the observed variance
# of a feature that is always exactly 1.0 is zero.
SCALE_FLOOR: Dict[str, float] = {f: 0.0 for f in FEATURES}
for _f in ("conn_attempts", "failed_logins", "unique_dst_ips",
           "port_diversity", "reconnects", "device_event_rate", "cmd_rate"):
    SCALE_FLOOR[_f] = 0.5
SCALE_FLOOR["payload_entropy"] = 0.05
SCALE_FLOOR["cpu_usage"] = 0.5
SCALE_FLOOR["mem_usage"] = 0.5
SCALE_FLOOR_VEC = np.array([SCALE_FLOOR[f] for f in FEATURES], dtype=np.float64)


# ---------------------------------------------------------------------------
# STEP 3 holographic planes.  The hologram is not one state vector but a set
# of partial projections of the device.  The full state is reconstructed from
# all of them, and the coherence between projections is itself a signal: an
# attacker who fakes one plane rarely keeps the others physically consistent.
# ---------------------------------------------------------------------------
PLANES: Dict[str, List[str]] = {
    "resource": ["cpu_usage", "mem_usage", "power_draw"],
    "network": ["net_in_kbps", "net_out_kbps", "packet_rate",
                "avg_pkt_size", "payload_entropy"],
    "access": ["conn_attempts", "failed_logins", "reconnects",
               "session_duration"],
    "topology": ["unique_dst_ips", "port_diversity"],
    "actuation": ["cmd_rate", "device_event_rate"],
}
PLANE_NAMES: List[str] = list(PLANES)
PLANE_INDEX: Dict[str, List[int]] = {
    name: [FEATURE_INDEX[f] for f in feats] for name, feats in PLANES.items()
}


class DeviceType(str, Enum):
    SMART_CAMERA = "smart_camera"
    SMART_BULB = "smart_bulb"
    SMART_PLUG = "smart_plug"
    SMART_LOCK = "smart_lock"
    TEMP_SENSOR = "temperature_sensor"
    SMART_SPEAKER = "smart_speaker"


DEVICE_TYPES: List[str] = [d.value for d in DeviceType]
DEVICE_TYPE_INDEX: Dict[str, int] = {d: i for i, d in enumerate(DEVICE_TYPES)}


class ThreatClass(str, Enum):
    NORMAL = "normal"
    DDOS = "ddos"
    BOTNET_C2 = "botnet_c2"
    BRUTE_FORCE = "brute_force"
    PORT_SCAN = "port_scan"
    DATA_EXFIL = "data_exfiltration"
    FIRMWARE_TAMPER = "firmware_tamper"


THREAT_CLASSES: List[str] = [t.value for t in ThreatClass]
THREAT_INDEX: Dict[str, int] = {t: i for i, t in enumerate(THREAT_CLASSES)}
ATTACK_CLASSES: List[str] = [t for t in THREAT_CLASSES if t != "normal"]
NORMAL_IDX: int = THREAT_INDEX["normal"]


class RiskLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Decision(str, Enum):
    ACCEPTED = "ACCEPTED"
    QUARANTINED = "QUARANTINED"


class PoisonStrategy(str, Enum):
    CLEAN = "clean"
    LABEL_FLIP = "label_flip"
    GRADUAL = "gradual_poisoning"
    BACKDOOR = "backdoor"
    SYBIL = "sybil"
    CLEAN_LABEL = "clean_label"


POISON_STRATEGIES: List[str] = [p.value for p in PoisonStrategy]
ATTACK_STRATEGIES: List[str] = [p for p in POISON_STRATEGIES if p != "clean"]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass
class Telemetry:
    """One observation emitted by a simulated IoT device (STEP 1)."""
    device_id: str
    device_type: str
    timestamp: float
    values: np.ndarray
    ground_truth: str = "normal"     # simulation bookkeeping only
    sequence: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "ground_truth": self.ground_truth,
            "features": {f: round(float(v), 3)
                         for f, v in zip(FEATURES, self.values)},
        }


@dataclass
class ThreatVerdict:
    """What the edge detector concluded about one observation (STEP 6)."""
    device_id: str
    predicted_class: str
    confidence: float
    risk_level: str
    probabilities: Dict[str, float] = field(default_factory=dict)
    counterfactual_consistency: float = 1.0
    plane_deviation: Dict[str, float] = field(default_factory=dict)
    anomalous_planes: List[str] = field(default_factory=list)
    twin_flagged: bool = False
    model_version: int = 0
    ground_truth: str = "normal"
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelUpdate:
    """A candidate training contribution arriving at the gateway (STEP 7).

    In a federated consumer-IoT deployment these arrive from devices, hubs or
    a vendor cloud, any of which may be attacker-controlled.
    """
    update_id: str
    source: str
    X: np.ndarray                     # (n, N_FEATURES) raw telemetry
    y: np.ndarray                     # (n,) threat-class indices
    device_type_ids: Optional[np.ndarray] = None
    declared_strategy: str = "clean"  # simulation ground truth.  The validator
                                      # never reads it; it exists only so the
                                      # console can score the defence.
    created_at: float = field(default_factory=time.time)
    round_index: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def n_samples(self) -> int:
        return int(self.X.shape[0])

    @staticmethod
    def new(source: str, X: np.ndarray, y: np.ndarray,
            device_type_ids: Optional[np.ndarray] = None,
            **kw: Any) -> "ModelUpdate":
        dt = (None if device_type_ids is None
              else np.asarray(device_type_ids, dtype=np.int64))
        return ModelUpdate(update_id=new_id("upd"), source=source,
                           X=np.asarray(X, dtype=np.float64),
                           y=np.asarray(y, dtype=np.int64),
                           device_type_ids=dt, **kw)

    def label_summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for idx, count in zip(*np.unique(self.y, return_counts=True)):
            out[THREAT_CLASSES[int(idx)]] = int(count)
        return out

    def brief(self) -> Dict[str, Any]:
        return {"update_id": self.update_id, "source": self.source,
                "n_samples": self.n_samples,
                "declared_strategy": self.declared_strategy,
                "labels": self.label_summary(),
                "created_at": self.created_at,
                "round_index": self.round_index,
                "meta": self.meta}


@dataclass
class ValidationReport:
    """Outcome of counterfactual validation of one update (STEP 8)."""
    update_id: str
    source: str
    decision: str
    consistency_score: float
    attack_agreement: float
    benign_agreement: float
    stability: float
    plane_coherence: float
    label_shift: float
    reputation: float
    threshold: float
    suspected_strategy: str
    strategy_confidence: float
    n_samples: int
    declared_strategy: str = "clean"
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ModelVersion:
    """An entry in the secure model registry (STEP 11)."""
    version: int
    path: str
    accuracy: float
    macro_f1: float
    false_positive_rate: float
    false_negative_rate: float
    poison_resistance: float
    trusted: bool
    created_at: float = field(default_factory=time.time)
    parent: Optional[int] = None
    notes: str = ""
    n_train: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clamp_features(X: np.ndarray) -> np.ndarray:
    """Clamp a feature matrix (or a single vector) into physical range."""
    original = np.asarray(X, dtype=np.float64)
    arr = np.atleast_2d(original).copy()
    for i, name in enumerate(FEATURES):
        lo, hi = FEATURE_BOUNDS[name]
        np.clip(arr[:, i], lo, hi, out=arr[:, i])
    return arr.reshape(original.shape)


def risk_from_confidence(predicted: str, confidence: float) -> str:
    """Map a class prediction plus confidence onto an operator-facing risk."""
    if predicted == "normal":
        return RiskLevel.NONE.value
    if confidence >= 0.90:
        return RiskLevel.CRITICAL.value
    if confidence >= 0.70:
        return RiskLevel.HIGH.value
    if confidence >= 0.45:
        return RiskLevel.MEDIUM.value
    return RiskLevel.LOW.value
