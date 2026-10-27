"""STEP 6: turning raw telemetry into what the detector actually sees.

Three transforms, each doing a specific job:

* **log compression** on the heavy-tailed counters.  Packet rate spans four
  orders of magnitude between an idle bulb and a camera under flood; without
  compression a tree spends all its depth splitting the top of that range.
* **cross-plane ratios.**  These are the physics.  A device reporting huge
  outbound throughput while its packet rate and packet size cannot possibly
  account for it is internally inconsistent, and no attack profile bothers to
  keep those three numbers mutually consistent.  These ratios are also what
  the plane-coherence term of the CCS is computed from in STEP 8.
* **device type**, one-hot.  The single most important context there is: 2 Mb/s
  outbound is a Tuesday for a camera and an emergency for a bulb.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from ..schemas import DEVICE_TYPES, FEATURE_INDEX, FEATURES, N_FEATURES

# Counters that need log compression before a tree ever sees them.
_LOG_FEATURES = [
    "net_in_kbps", "net_out_kbps", "packet_rate", "conn_attempts",
    "failed_logins", "unique_dst_ips", "port_diversity", "cmd_rate",
    "avg_pkt_size", "session_duration", "reconnects", "device_event_rate",
    "power_draw",
]
_LOG_IDX = [FEATURE_INDEX[f] for f in _LOG_FEATURES]

RATIO_NAMES: List[str] = [
    "r_out_over_in",       # exfiltration and flooding both skew this
    "r_pkts_per_conn",     # floods: many packets, few connections
    "r_volume_coherence",  # does throughput agree with rate x size?
    "r_fail_per_conn",     # brute force
    "r_ports_per_host",    # port scan
    "r_power_per_cpu",     # firmware tamper: compute up, power inconsistent
    "r_events_per_cmd",    # actuation-plane consistency
    "r_entropy_x_size",    # encrypted bulk transfer
]

FEATURE_NAMES: List[str] = (
    [f"log_{f}" if f in _LOG_FEATURES else f for f in FEATURES]
    + RATIO_NAMES
    + [f"is_{d}" for d in DEVICE_TYPES]
)
N_ENGINEERED = len(FEATURE_NAMES)


def _col(X: np.ndarray, name: str) -> np.ndarray:
    return X[:, FEATURE_INDEX[name]]


def cross_plane_ratios(X: np.ndarray) -> np.ndarray:
    """The (n, 8) block of physics ratios. Also used by plane-coherence."""
    X = np.atleast_2d(np.asarray(X, dtype=np.float64))
    net_in = _col(X, "net_in_kbps")
    net_out = _col(X, "net_out_kbps")
    pkt = _col(X, "packet_rate")
    size = _col(X, "avg_pkt_size")
    conn = _col(X, "conn_attempts")
    fail = _col(X, "failed_logins")
    hosts = _col(X, "unique_dst_ips")
    ports = _col(X, "port_diversity")
    cpu = _col(X, "cpu_usage")
    power = _col(X, "power_draw")
    cmd = _col(X, "cmd_rate")
    events = _col(X, "device_event_rate")
    entropy = _col(X, "payload_entropy")

    # Throughput implied by rate x size, in kb/s, versus throughput reported.
    implied = pkt * size * 8.0 / 1000.0
    coherence = np.log1p(net_out) - np.log1p(implied)

    out = np.column_stack([
        np.log1p(net_out) - np.log1p(net_in),
        np.log1p(pkt) - np.log1p(conn),
        coherence,
        fail / (conn + 1.0),
        ports / (hosts + 1.0),
        power / (cpu + 1.0),
        events / (cmd + 0.1),
        entropy * np.log1p(size),
    ])
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def engineer(X: np.ndarray,
             device_type_ids: Optional[np.ndarray] = None) -> np.ndarray:
    """Raw telemetry -> the detector's input matrix."""
    X = np.atleast_2d(np.asarray(X, dtype=np.float64))
    if X.shape[1] != N_FEATURES:                       # pragma: no cover
        raise ValueError(f"expected {N_FEATURES} raw features, got {X.shape[1]}")

    base = X.copy()
    base[:, _LOG_IDX] = np.log1p(np.maximum(base[:, _LOG_IDX], 0.0))

    onehot = np.zeros((X.shape[0], len(DEVICE_TYPES)))
    if device_type_ids is not None:
        ids = np.asarray(device_type_ids, dtype=np.int64).ravel()
        valid = (ids >= 0) & (ids < len(DEVICE_TYPES))
        onehot[np.arange(X.shape[0])[valid], ids[valid]] = 1.0

    return np.hstack([base, cross_plane_ratios(X), onehot])
