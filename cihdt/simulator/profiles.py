"""STEP 1: what each consumer IoT device looks like, healthy and compromised.

Two tables live here.

``DEVICE_PROFILES`` gives a (mean, std) for every feature of every device type.
These are the numbers that make a bulb and a camera genuinely different
problems: a camera streaming 2 Mb/s outbound is boring, while a bulb doing the
same thing is a catastrophe.  A detector that cannot tell them apart is useless
on a real home network, which is why device type is a model input.

``ATTACK_PROFILES`` says how each threat class deforms a healthy baseline.
Each entry is ``feature -> (multiplier, addend)``, applied with an intensity so
the same attack can be run loud or stealthy.  Crucially the attacks are spread
across different *holographic planes* -- a port scan wrecks the topology plane
while barely touching resources, and a firmware tamper does the opposite.  That
is what makes plane coherence an informative signal later on.
"""
from __future__ import annotations

from typing import Dict, Tuple

from ..schemas import DEVICE_TYPES, FEATURES

# feature -> (mean, standard deviation)
Profile = Dict[str, Tuple[float, float]]

DEVICE_PROFILES: Dict[str, Profile] = {
    "smart_camera": {
        "cpu_usage": (32.0, 6.0), "mem_usage": (45.0, 6.0),
        "net_in_kbps": (120.0, 30.0), "net_out_kbps": (2200.0, 400.0),
        "packet_rate": (900.0, 150.0), "conn_attempts": (2.0, 1.0),
        "failed_logins": (0.02, 0.15), "unique_dst_ips": (3.0, 1.0),
        "port_diversity": (4.0, 1.0), "cmd_rate": (0.5, 0.4),
        "payload_entropy": (7.2, 0.2), "avg_pkt_size": (1100.0, 120.0),
        "session_duration": (900.0, 200.0), "reconnects": (0.05, 0.25),
        "device_event_rate": (6.0, 3.0), "power_draw": (5.5, 0.8),
    },
    "smart_bulb": {
        "cpu_usage": (4.0, 1.5), "mem_usage": (12.0, 3.0),
        "net_in_kbps": (3.0, 1.0), "net_out_kbps": (2.0, 1.0),
        "packet_rate": (4.0, 2.0), "conn_attempts": (1.0, 0.5),
        "failed_logins": (0.01, 0.10), "unique_dst_ips": (2.0, 0.5),
        "port_diversity": (2.0, 0.5), "cmd_rate": (0.8, 0.6),
        "payload_entropy": (3.1, 0.4), "avg_pkt_size": (180.0, 40.0),
        "session_duration": (600.0, 180.0), "reconnects": (0.05, 0.22),
        "device_event_rate": (1.2, 1.0), "power_draw": (9.0, 3.0),
    },
    "smart_plug": {
        "cpu_usage": (5.0, 2.0), "mem_usage": (14.0, 3.0),
        "net_in_kbps": (4.0, 1.5), "net_out_kbps": (3.0, 1.2),
        "packet_rate": (5.0, 2.0), "conn_attempts": (1.0, 0.5),
        "failed_logins": (0.01, 0.10), "unique_dst_ips": (2.0, 0.5),
        "port_diversity": (2.0, 0.5), "cmd_rate": (0.6, 0.5),
        "payload_entropy": (3.0, 0.4), "avg_pkt_size": (190.0, 45.0),
        "session_duration": (700.0, 200.0), "reconnects": (0.05, 0.22),
        "device_event_rate": (0.8, 0.7), "power_draw": (60.0, 45.0),
    },
    "smart_lock": {
        "cpu_usage": (6.0, 2.0), "mem_usage": (18.0, 4.0),
        "net_in_kbps": (5.0, 2.0), "net_out_kbps": (4.0, 1.5),
        "packet_rate": (6.0, 2.0), "conn_attempts": (2.0, 1.0),
        "failed_logins": (0.05, 0.22), "unique_dst_ips": (2.0, 0.6),
        "port_diversity": (2.0, 0.6), "cmd_rate": (1.1, 0.8),
        "payload_entropy": (3.6, 0.4), "avg_pkt_size": (210.0, 50.0),
        "session_duration": (300.0, 120.0), "reconnects": (0.08, 0.28),
        "device_event_rate": (0.9, 0.7), "power_draw": (2.2, 0.5),
    },
    "temperature_sensor": {
        "cpu_usage": (2.0, 0.8), "mem_usage": (8.0, 2.0),
        "net_in_kbps": (1.5, 0.6), "net_out_kbps": (1.2, 0.5),
        "packet_rate": (2.0, 1.0), "conn_attempts": (0.6, 0.3),
        "failed_logins": (0.005, 0.07), "unique_dst_ips": (1.0, 0.3),
        "port_diversity": (1.0, 0.3), "cmd_rate": (0.2, 0.2),
        "payload_entropy": (2.4, 0.3), "avg_pkt_size": (120.0, 20.0),
        "session_duration": (1200.0, 260.0), "reconnects": (0.03, 0.18),
        "device_event_rate": (2.0, 0.4), "power_draw": (0.6, 0.15),
    },
    "smart_speaker": {
        "cpu_usage": (18.0, 7.0), "mem_usage": (38.0, 8.0),
        "net_in_kbps": (350.0, 180.0), "net_out_kbps": (260.0, 140.0),
        "packet_rate": (220.0, 110.0), "conn_attempts": (4.0, 2.0),
        "failed_logins": (0.03, 0.18), "unique_dst_ips": (8.0, 4.0),
        "port_diversity": (9.0, 4.0), "cmd_rate": (2.5, 2.0),
        "payload_entropy": (6.5, 0.6), "avg_pkt_size": (700.0, 200.0),
        "session_duration": (500.0, 200.0), "reconnects": (0.12, 0.32),
        "device_event_rate": (3.0, 2.5), "power_draw": (4.5, 1.2),
    },
}

# Sanity: every profile must cover the whole feature space.
for _dt in DEVICE_TYPES:
    _missing = set(FEATURES) - set(DEVICE_PROFILES[_dt])
    if _missing:                                          # pragma: no cover
        raise RuntimeError(f"{_dt} profile missing {_missing}")

# feature -> (multiplier, addend).  Applied as
#   value = base * (1 + (mult - 1) * intensity) + addend * intensity
Deform = Dict[str, Tuple[float, float]]

ATTACK_PROFILES: Dict[str, Deform] = {
    # Volumetric flood: enormous packet counts, tiny packets, CPU pinned.
    "ddos": {
        "cpu_usage": (2.4, 0.0), "mem_usage": (1.5, 0.0),
        "net_out_kbps": (40.0, 0.0), "packet_rate": (60.0, 0.0),
        "conn_attempts": (25.0, 0.0), "avg_pkt_size": (0.35, 0.0),
        "unique_dst_ips": (6.0, 0.0), "power_draw": (1.30, 0.0),
        "session_duration": (0.40, 0.0),
    },
    # Beaconing to a command-and-control host: many short sessions, high
    # entropy, lots of distinct endpoints, but almost no volume.
    "botnet_c2": {
        "cpu_usage": (1.35, 0.0), "net_out_kbps": (3.0, 0.0),
        "conn_attempts": (6.0, 0.0), "unique_dst_ips": (12.0, 0.0),
        "port_diversity": (8.0, 0.0), "payload_entropy": (1.0, 1.2),
        "reconnects": (1.0, 4.0), "session_duration": (0.25, 0.0),
    },
    # Credential stuffing against the device itself.
    "brute_force": {
        "cpu_usage": (1.5, 0.0), "net_in_kbps": (2.5, 0.0),
        "conn_attempts": (22.0, 0.0), "failed_logins": (1.0, 180.0),
        "session_duration": (0.15, 0.0), "reconnects": (1.0, 9.0),
    },
    # Reconnaissance: the topology plane explodes, everything else is quiet.
    "port_scan": {
        "unique_dst_ips": (40.0, 0.0), "port_diversity": (220.0, 0.0),
        "packet_rate": (12.0, 0.0), "avg_pkt_size": (0.25, 0.0),
        "conn_attempts": (18.0, 0.0), "session_duration": (0.05, 0.0),
        "cpu_usage": (1.2, 0.0),
    },
    # Slow bulk theft: sustained high-entropy outbound over long sessions.
    "data_exfiltration": {
        "net_out_kbps": (22.0, 0.0), "avg_pkt_size": (1.7, 0.0),
        "payload_entropy": (1.0, 1.6), "session_duration": (3.2, 0.0),
        "cpu_usage": (1.4, 0.0), "unique_dst_ips": (2.0, 0.0),
        "packet_rate": (6.0, 0.0),
    },
    # Malicious firmware: the actuation and resource planes go wrong while the
    # network looks almost ordinary.  The physical device misbehaves.
    "firmware_tamper": {
        "cpu_usage": (2.8, 0.0), "mem_usage": (1.9, 0.0),
        "cmd_rate": (14.0, 0.0), "device_event_rate": (7.0, 0.0),
        "power_draw": (1.8, 0.0), "reconnects": (1.0, 6.0),
        "payload_entropy": (1.0, 0.9), "net_in_kbps": (4.0, 0.0),
    },
}

# Which device types each attack realistically targets first.  Used by the
# console to suggest sensible attacks, never to constrain what the operator
# is allowed to launch.
TYPICAL_TARGETS: Dict[str, Tuple[str, ...]] = {
    "smart_camera": ("ddos", "data_exfiltration", "botnet_c2"),
    "smart_bulb": ("botnet_c2", "firmware_tamper"),
    "smart_plug": ("botnet_c2", "ddos"),
    "smart_lock": ("brute_force", "firmware_tamper"),
    "temperature_sensor": ("botnet_c2", "port_scan"),
    "smart_speaker": ("data_exfiltration", "botnet_c2", "port_scan"),
}

CATALOGUE_TEXT: Dict[str, Dict[str, str]] = {
    "smart_camera": {
        "label": "Smart Camera",
        "icon": "camera",
        "blurb": "Streams video continuously. Heavy outbound traffic is normal "
                 "here, which is exactly what makes data theft hard to spot.",
    },
    "smart_bulb": {
        "label": "Smart Bulb",
        "icon": "bulb",
        "blurb": "Nearly silent on the network. Any sustained traffic at all "
                 "is worth investigating.",
    },
    "smart_plug": {
        "label": "Smart Plug",
        "icon": "plug",
        "blurb": "Low compute, wildly variable power draw. A favourite botnet "
                 "foothold because nobody ever patches them.",
    },
    "smart_lock": {
        "label": "Smart Lock",
        "icon": "lock",
        "blurb": "Physical security depends on it. A failed-login spike matters "
                 "more here than anywhere else in the house.",
    },
    "temperature_sensor": {
        "label": "Temperature Sensor",
        "icon": "sensor",
        "blurb": "Tiny, highly predictable traffic. The most stable baseline in "
                 "the fleet, so deviations stand out immediately.",
    },
    "smart_speaker": {
        "label": "Smart Speaker",
        "icon": "speaker",
        "blurb": "Bursty voice traffic reaching many endpoints. A noisy "
                 "baseline that hides a great deal.",
    },
}

# The mix the console offers as a starting point on the setup screen.
SUGGESTED_LAYOUT: Dict[str, int] = {
    "smart_camera": 2,
    "smart_bulb": 2,
    "smart_plug": 1,
    "smart_lock": 1,
    "temperature_sensor": 1,
    "smart_speaker": 1,
}
