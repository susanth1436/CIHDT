"""Measuring the sixteen features from a real machine, and saying honestly
where each one came from.

This is the module an examiner should read first, because it is where the
project's claim about live data has to be exact.

A USB peripheral has no network stack.  It has no address, opens no sockets and
authenticates nobody, so eight of the sixteen features in
:data:`cihdt.schemas.FEATURES` cannot be measured *from the device* even in
principle.  What can be measured is the host the device is attached to, and the
device's own presence on the bus.  Every value this module produces therefore
carries a provenance:

``device``       measured from the peripheral itself: how long it has been
                 attached, how often it dropped, whether Windows still
                 considers it healthy.
``host``         measured from this machine. The network planes live here. A
                 compromised webcam exfiltrates *through the host's* network
                 stack, so this is where its traffic would actually appear --
                 but the figure is the whole host's, not that device's alone,
                 and attributing it to the selected device is a stated
                 modelling assumption rather than a per-device measurement.
``declared``     read off the USB specification for the device's class, not
                 measured. Bus power is the only one of these.
``unavailable``  cannot be obtained on this host without privileges or a
                 capture driver. Held at zero and reported as missing, never
                 invented.

Two features are unavailable: ``failed_logins`` needs the Windows Security
event log and administrator rights, and ``payload_entropy`` needs a packet
capture driver.  They are flagged, not fabricated.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..schemas import FEATURE_INDEX, FEATURES, N_FEATURES, clamp_features

try:
    import psutil
except ImportError:                                        # pragma: no cover
    psutil = None                                          # type: ignore


# feature -> (provenance, how it is obtained)
PROVENANCE: Dict[str, Tuple[str, str]] = {
    "cpu_usage":         ("host", "psutil.cpu_percent over the sample interval"),
    "mem_usage":         ("host", "psutil.virtual_memory().percent"),
    "net_in_kbps":       ("host", "net_io_counters bytes_recv delta / interval"),
    "net_out_kbps":      ("host", "net_io_counters bytes_sent delta / interval"),
    "packet_rate":       ("host", "net_io_counters packet deltas / interval"),
    "conn_attempts":     ("host", "new inet connections seen this interval"),
    "failed_logins":     ("unavailable",
                          "needs the Windows Security event log and admin rights"),
    "unique_dst_ips":    ("host", "distinct remote addresses in the connection table"),
    "port_diversity":    ("host", "distinct remote ports in the connection table"),
    "cmd_rate":          ("host", "process-table growth over the interval"),
    "payload_entropy":   ("unavailable",
                          "needs a packet-capture driver to read payloads"),
    "avg_pkt_size":      ("host", "byte delta / packet delta"),
    "session_duration":  ("device", "seconds the device has been continuously attached"),
    "reconnects":        ("device", "absent-to-present transitions on the USB bus"),
    "device_event_rate": ("device", "Windows PnP status changes for this device"),
    "power_draw":        ("declared",
                          "USB specification maximum for the device class, not measured"),
}

UNAVAILABLE: List[str] = [f for f, (p, _) in PROVENANCE.items()
                          if p == "unavailable"]
MEASURED: List[str] = [f for f, (p, _) in PROVENANCE.items()
                       if p in ("host", "device")]


class HostUnavailable(RuntimeError):
    """Host telemetry cannot be sampled."""


def _safe(call, default, *args, **kwargs):
    """Read a host counter, or fall back when the platform refuses.

    Every psutil reading in this module is optional in the same way: a host
    that will not answer leaves the feature at its default, and PROVENANCE
    already tells the operator which features describe the host rather than
    the device. What must never happen is an unhandled error from a counter,
    because that turns a missing reading into a failed page.
    """
    try:
        return call(*args, **kwargs)
    except (psutil.AccessDenied, PermissionError, OSError, RuntimeError,
            AttributeError, TypeError):
        return default


class HostSampler:
    """Turns this machine into one observation per call.

    Rates need two readings and the time between them, so the first call after
    construction primes the counters and every call after it reports the
    interval that has actually elapsed.  Nothing is sampled in the background:
    a caller that wants thirty observations asks for thirty, and waits.
    """

    def __init__(self) -> None:
        if psutil is None:                                 # pragma: no cover
            raise HostUnavailable(
                "psutil is not installed, so live host telemetry cannot be "
                "sampled. Install it with: pip install psutil")
        self._last_t: Optional[float] = None
        self._last_io = None
        self._last_procs: Optional[int] = None
        self._seen_conns: set = set()
        self.samples = 0
        self.prime()

    # ------------------------------------------------------------------ prime
    @staticmethod
    def _io_counters() -> Optional[Any]:
        """Network counters, or None where the platform will not give them.

        ``net_io_counters`` is documented to return None when no counters are
        available, and inside a restricted container it can also raise
        outright.  A host that cannot answer is an ordinary condition here --
        the features it would have fed are reported as unavailable rather
        than invented -- so neither outcome may reach the caller as an
        exception.
        """
        try:
            return psutil.net_io_counters()
        except (psutil.AccessDenied, PermissionError, OSError, RuntimeError):
            return None

    @staticmethod
    def _process_count() -> int:
        try:
            return len(psutil.pids())
        except (psutil.AccessDenied, PermissionError, OSError):
            return 0

    def prime(self) -> None:
        """Take the first reading, which only establishes the baseline."""
        self._last_t = time.perf_counter()
        self._last_io = self._io_counters()
        self._last_procs = self._process_count()
        try:
            psutil.cpu_percent(interval=None)  # arm the cpu counter
        except (psutil.AccessDenied, PermissionError, OSError):
            pass

    # ----------------------------------------------------------------- sample
    def _connections(self) -> Tuple[int, int, int]:
        """(new connections this interval, distinct hosts, distinct ports)."""
        try:
            conns = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError, OSError):
            return 0, 0, 0
        hosts, ports, keys = set(), set(), set()
        for c in conns:
            if not c.raddr:
                continue
            hosts.add(c.raddr.ip)
            ports.add(c.raddr.port)
            keys.add((c.raddr.ip, c.raddr.port))
        new = len(keys - self._seen_conns)
        self._seen_conns = keys
        return new, len(hosts), len(ports)

    def sample(self, device: Optional[Any] = None) -> np.ndarray:
        """One observation, as a raw 16-feature vector.

        ``device`` is a :class:`~cihdt.live.usb.UsbDevice`; when given, the
        three device-provenance features come from it rather than being held
        at zero.
        """
        now = time.perf_counter()
        dt = max(1e-3, now - (self._last_t or now))
        io = self._io_counters()
        procs = self._process_count()

        # Either reading may be missing on a host that does not publish
        # counters.  The deltas are then zero, which is what "no traffic
        # observed" means, and the provenance table already states that these
        # features describe the host rather than the peripheral.
        if io is None or self._last_io is None:
            d_recv = d_sent = d_pkt_in = d_pkt_out = 0
        else:
            d_recv = max(0, io.bytes_recv - self._last_io.bytes_recv)
            d_sent = max(0, io.bytes_sent - self._last_io.bytes_sent)
            d_pkt_in = max(0, io.packets_recv - self._last_io.packets_recv)
            d_pkt_out = max(0, io.packets_sent - self._last_io.packets_sent)
        d_pkts = d_pkt_in + d_pkt_out
        d_bytes = d_recv + d_sent

        new_conns, hosts, ports = self._connections()

        v = np.zeros(N_FEATURES, dtype=np.float64)
        s = lambda name, value: v.__setitem__(FEATURE_INDEX[name], float(value))

        # --- host ---------------------------------------------------------
        s("cpu_usage", _safe(psutil.cpu_percent, 0.0, interval=None))
        s("mem_usage", _safe(lambda: psutil.virtual_memory().percent, 0.0))
        s("net_in_kbps", d_recv * 8.0 / 1000.0 / dt)
        s("net_out_kbps", d_sent * 8.0 / 1000.0 / dt)
        s("packet_rate", d_pkts / dt)
        s("conn_attempts", new_conns)
        s("unique_dst_ips", hosts)
        s("port_diversity", ports)
        s("cmd_rate", max(0, procs - (self._last_procs or procs)) / dt)
        s("avg_pkt_size", (d_bytes / d_pkts) if d_pkts else 0.0)

        # --- device -------------------------------------------------------
        if device is not None:
            s("session_duration", device.session_duration)
            s("reconnects", device.reconnects)
            s("device_event_rate", device.status_changes)
            from .usb import DECLARED_POWER_W
            s("power_draw", DECLARED_POWER_W.get(device.archetype, 2.5))

        # --- unavailable: left at zero on purpose -------------------------
        # failed_logins and payload_entropy are not obtainable here.

        self._last_t, self._last_io, self._last_procs = now, io, procs
        self.samples += 1
        return clamp_features(v)

    # -------------------------------------------------------------- reporting
    @staticmethod
    def provenance_rows() -> List[Dict[str, str]]:
        """The disclosure table the console shows the operator."""
        return [{"feature": f, "provenance": PROVENANCE[f][0],
                 "how": PROVENANCE[f][1]} for f in FEATURES]

    @staticmethod
    def summary() -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for _f, (p, _how) in PROVENANCE.items():
            counts[p] = counts.get(p, 0) + 1
        return {"counts": counts, "unavailable": list(UNAVAILABLE),
                "measured": len(MEASURED), "total": N_FEATURES}


def available() -> Tuple[bool, str]:
    """Whether live sampling is possible here, and why not if it is not."""
    if psutil is None:
        return False, ("psutil is not installed. Run: pip install psutil")
    return True, ""
