"""Real USB devices attached to this machine, and how present they are.

Enumeration goes through WMI (``Win32_PnPEntity``), which is the only route
that needs no driver, no elevation and no third-party package.  It costs about
a second per call, so it is cached: the operator refreshes it when they plug
something in, and the per-tick sampler reads the cache rather than paying that
cost on every observation.

What this module can honestly report about a USB peripheral is narrow, and the
narrowness is the point.  A USB webcam is not a network node -- it has no
address, opens no sockets and authenticates nobody -- so the only things
genuinely measurable about *the device itself* are whether it is present, how
long it has been present without interruption, how often it has dropped and
come back, and whether Windows considers it healthy.  Those four feed the
actuation and access planes.  Everything on the network planes is measured on
the host instead, and :mod:`cihdt.live.host` says so explicitly.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Windows PnP classes mapped onto the nearest archetype in the project's
# taxonomy.  The detector one-hots device type, so a live device has to be
# placed somewhere; the operator can override the guess in the console.
CLASS_TO_ARCHETYPE: Dict[str, str] = {
    "camera": "smart_camera",
    "image": "smart_camera",
    "media": "smart_speaker",
    "audioendpoint": "smart_speaker",
    "sound": "smart_speaker",
    "bluetooth": "smart_plug",
    "net": "smart_plug",
    "keyboard": "smart_lock",
    "mouse": "smart_lock",
    "hidclass": "smart_lock",
    "usb": "temperature_sensor",
    "usbdevice": "temperature_sensor",
}
DEFAULT_ARCHETYPE = "smart_plug"

# USB-declared maximum bus power, in watts.  This is what the device is
# *allowed* to draw, read off the specification for its bus generation -- not a
# measurement.  Anything reporting it must say so.
DECLARED_POWER_W: Dict[str, float] = {
    "smart_camera": 2.5,          # USB 2.0 high power, 500 mA at 5 V
    "smart_speaker": 2.5,
    "smart_plug": 2.5,
    "smart_lock": 0.5,            # HID devices are typically 100 mA
    "temperature_sensor": 0.5,
}

_PS = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
       "Bypass", "-Command"]
_QUERY = (
    "Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | "
    "Where-Object { $_.PNPDeviceID -like 'USB\\*' } | "
    "Select-Object Name,PNPClass,Status,PNPDeviceID,Manufacturer,"
    "ConfigManagerErrorCode | "
    "ConvertTo-Json -Compress"
)

_VID_PID = re.compile(r"VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})")

# Windows ConfigManagerErrorCode.  "Error" on its own tells an operator
# nothing: a camera behind a privacy shutter and a camera with a dead driver
# both report it, and only one of them is a problem worth chasing.
ERROR_CODES: Dict[int, str] = {
    0: "working normally",
    1: "not configured correctly",
    3: "driver may be corrupted, or the system is low on memory",
    10: "device cannot start",
    12: "cannot find enough free resources",
    14: "needs a restart to work",
    18: "drivers need reinstalling",
    19: "registry entry is corrupt",
    21: "Windows is removing it",
    22: "disabled -- by a privacy switch, a function key, or Device Manager",
    24: "not present, or not working",
    28: "drivers are not installed",
    31: "not working properly: the driver failed to load",
    43: "Windows stopped it after the device reported a failure",
    45: "not currently connected",
    47: "prepared for safe removal",
    52: "driver signature could not be verified",
}


class UsbUnavailable(RuntimeError):
    """USB enumeration is not possible on this host."""


@dataclass
class UsbDevice:
    """One real peripheral, and how it has behaved since we started watching."""
    instance_id: str
    name: str
    pnp_class: str
    status: str
    manufacturer: str = ""
    vid: str = ""
    pid: str = ""
    error_code: int = 0

    present: bool = True
    first_seen: float = field(default_factory=time.time)
    present_since: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    reconnects: int = 0            # absent -> present transitions
    status_changes: int = 0        # Windows changed its mind about health

    @property
    def archetype(self) -> str:
        return CLASS_TO_ARCHETYPE.get((self.pnp_class or "").lower(),
                                      DEFAULT_ARCHETYPE)

    @property
    def session_duration(self) -> float:
        """Seconds this device has been continuously attached."""
        return max(0.0, time.time() - self.present_since)

    @property
    def healthy(self) -> bool:
        return self.status.upper() == "OK"

    @property
    def reason(self) -> str:
        """Why Windows reports this device the way it does."""
        return ERROR_CODES.get(int(self.error_code),
                               f"Windows reports code {self.error_code}")

    def slug(self) -> str:
        """A short stable id derived from the device, safe in a URL.

        The id is keyed off a digest of the *whole* instance id, not its last
        segment.  A composite peripheral exposes one entry per interface --
        a webcam with a microphone enumerates as MI_00 for video and MI_02 for
        audio -- and those entries share a VID, a PID and a trailing segment,
        differing only in a part an abbreviation throws away.  Hashing the full
        string keeps them distinct, and keeps the `&` that Windows puts in
        instance ids out of a URL.
        """
        digest = hashlib.sha1(self.instance_id.encode("utf-8")).hexdigest()[:8]
        if self.vid and self.pid:
            return f"usb_{self.vid}_{self.pid}_{digest}".lower()
        return f"usb_{digest}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "slug": self.slug(),
            "name": self.name,
            "pnp_class": self.pnp_class,
            "status": self.status,
            "healthy": self.healthy,
            "error_code": int(self.error_code),
            "reason": self.reason,
            "manufacturer": self.manufacturer,
            "vid": self.vid,
            "pid": self.pid,
            "archetype": self.archetype,
            "present": self.present,
            "present_for_s": round(self.session_duration, 1),
            "reconnects": self.reconnects,
            "status_changes": self.status_changes,
            "declared_power_w": DECLARED_POWER_W.get(self.archetype, 2.5),
        }


def _run_query(timeout: float = 25.0) -> List[Dict[str, Any]]:
    try:
        proc = subprocess.run(_PS + [_QUERY], capture_output=True, text=True,
                              timeout=timeout,
                              creationflags=getattr(subprocess,
                                                    "CREATE_NO_WINDOW", 0))
    except FileNotFoundError as exc:
        raise UsbUnavailable(
            "PowerShell is not available, so USB devices cannot be "
            "enumerated on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise UsbUnavailable("USB enumeration timed out.") from exc

    text = (proc.stdout or "").strip()
    if not text:
        raise UsbUnavailable(
            "USB enumeration returned nothing. "
            + ((proc.stderr or "").strip()[:200] or
               "WMI may be unavailable on this host."))
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as exc:
        raise UsbUnavailable("Could not parse the USB device list.") from exc
    return [rows] if isinstance(rows, dict) else list(rows)


class UsbMonitor:
    """Keeps a cached view of attached USB devices and how stable they are.

    Nothing here polls.  The cache is refreshed when the operator asks for it
    and whenever a sampler decides the view is older than ``stale_after``, so
    the manual contract still holds: no work happens between requests.
    """

    def __init__(self, stale_after: float = 4.0) -> None:
        self.devices: Dict[str, UsbDevice] = {}
        self.stale_after = float(stale_after)
        self.last_refresh: Optional[float] = None
        self.last_error: Optional[str] = None
        self.refreshes = 0

    @property
    def available(self) -> bool:
        return self.last_error is None

    def refresh(self, force: bool = True) -> List[UsbDevice]:
        """Re-enumerate. Costs about a second, so callers should be sparing."""
        if (not force and self.last_refresh is not None
                and time.time() - self.last_refresh < self.stale_after):
            return self.present()

        try:
            rows = _run_query()
            self.last_error = None
        except UsbUnavailable as exc:
            self.last_error = str(exc)
            raise

        now = time.time()
        seen = set()
        for row in rows:
            iid = (row.get("PNPDeviceID") or "").strip()
            if not iid:
                continue
            seen.add(iid)
            status = (row.get("Status") or "Unknown").strip()
            name = (row.get("Name") or iid).strip()
            klass = (row.get("PNPClass") or "USB").strip()
            maker = (row.get("Manufacturer") or "").strip()
            match = _VID_PID.search(iid)
            vid, pid = (match.group(1), match.group(2)) if match else ("", "")
            try:
                code = int(row.get("ConfigManagerErrorCode") or 0)
            except (TypeError, ValueError):
                code = 0

            dev = self.devices.get(iid)
            if dev is None:
                self.devices[iid] = UsbDevice(
                    instance_id=iid, name=name, pnp_class=klass, status=status,
                    manufacturer=maker, vid=vid.upper(), pid=pid.upper(),
                    error_code=code)
                continue

            if not dev.present:                 # it came back
                dev.reconnects += 1
                dev.present_since = now
                dev.present = True
            if dev.status != status or dev.error_code != code:
                dev.status_changes += 1
                dev.status, dev.error_code = status, code
            dev.name, dev.pnp_class, dev.last_seen = name, klass, now

        for iid, dev in self.devices.items():   # anything that vanished
            if iid not in seen and dev.present:
                dev.present = False

        self.last_refresh = now
        self.refreshes += 1
        return self.present()

    def ensure_fresh(self) -> None:
        """Refresh only if the cached view has gone stale."""
        if (self.last_refresh is None
                or time.time() - self.last_refresh >= self.stale_after):
            try:
                self.refresh(force=True)
            except UsbUnavailable:
                pass                            # keep the last good view

    def present(self) -> List[UsbDevice]:
        return sorted((d for d in self.devices.values() if d.present),
                      key=lambda d: (d.pnp_class.lower(), d.name.lower()))

    def get(self, instance_id: str) -> Optional[UsbDevice]:
        return self.devices.get(instance_id)

    def by_slug(self, slug: str) -> Optional[UsbDevice]:
        return next((d for d in self.devices.values() if d.slug() == slug),
                    None)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "error": self.last_error,
            "last_refresh": self.last_refresh,
            "refreshes": self.refreshes,
            "present": [d.as_dict() for d in self.present()],
            "known": len(self.devices),
        }
