"""Enrolling a real USB peripheral through the visitor's browser.

Local live mode enumerates the USB bus with Windows WMI, which a hosted
console cannot do: the server has no bus to read, and the peripheral is
attached to a machine somewhere else entirely.  WebUSB closes exactly half of
that gap.  ``navigator.usb.requestDevice`` hands the page a device the visitor
explicitly picked, and its *descriptors* -- vendor and product id, class
triple, manufacturer and product strings, serial number, USB revision,
configurations and their endpoints -- are readable without claiming the
interface.  That matters, because a webcam is already claimed by the operating
system's UVC driver and will never be claimable from a page.

What the browser cannot supply is the other half.  Ten of the sixteen
features are host telemetry -- processor load, socket counts, packet rates --
and no browser API exposes them.  On a hosted console those values are
therefore sampled from the *server*, and :data:`WEBUSB_PROVENANCE` says so
for every one of them, in the same terms the local sampler uses.  The
arrangement is not a compromise introduced here: local live mode already
attributes host telemetry to the machine running the console rather than to
the peripheral, which is the assumption Section 8.2 of the report lists as
future work.  Hosting simply moves that machine further away, and the console
states where it is.

Everything arriving here came from a browser and is therefore untrusted.  The
payload is bounded, type-checked and clamped before it reaches a
:class:`~cihdt.live.usb.UsbDevice`; nothing is passed through on faith.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Dict, Mapping, Tuple

from .usb import UsbDevice

# USB base class codes, as published in the device descriptor, mapped onto the
# `pnp_class` vocabulary `UsbDevice.archetype` already understands.  A
# composite device declares 0x00 or 0xEF at the device level and puts the real
# class on each interface, so the interface list is consulted first.
USB_CLASS: Dict[int, str] = {
    0x01: "sound",        # audio
    0x02: "net",          # communications
    0x03: "hidclass",     # human interface
    0x06: "image",        # still imaging
    0x07: "usbdevice",    # printer
    0x08: "usbdevice",    # mass storage
    0x09: "usb",          # hub
    0x0A: "sound",        # CDC data
    0x0E: "camera",       # video
    0x0F: "usbdevice",    # personal healthcare
    0xE0: "bluetooth",    # wireless controller
}

MAX_STR = 120            # longest descriptor string accepted
MAX_INTERFACES = 64      # a plausible ceiling for a composite device


def _text(value: Any, limit: int = MAX_STR) -> str:
    """A descriptor string, reduced to characters a descriptor may contain.

    Control characters go, and so do angle brackets and the leading
    spreadsheet-formula characters.  Neither belongs in a manufacturer or
    product string, and both are only dangerous once the value reaches
    somewhere this module cannot see: the console escapes every name it
    renders, but a name also reaches the JSON and CSV exports, and a value
    that cannot carry markup or a formula cannot be mishandled downstream
    by code written later.
    """
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"[^\x20-\x7E]", "", value)
    cleaned = cleaned.replace("<", "").replace(">", "").strip()
    return cleaned.lstrip("=+@\t\r").strip()[:limit]


def _u16(value: Any) -> int:
    """A 16-bit descriptor field, or zero."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if 0 <= n <= 0xFFFF else 0


def _u8(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if 0 <= n <= 0xFF else 0


def classify(payload: Mapping[str, Any]) -> Tuple[str, str]:
    """Decide the device's class, and say which descriptor decided it.

    A composite peripheral carries class 0x00 (defer to interface) or 0xEF
    (miscellaneous) on the device descriptor, so the interface descriptors are
    the honest source.  The first interface whose class is recognised wins,
    which for a webcam-with-microphone is the video interface -- the same
    answer the Windows enumeration gives for its MI_00 entry.
    """
    device_class = _u8(payload.get("deviceClass"))
    if device_class not in (0x00, 0xEF) and device_class in USB_CLASS:
        return USB_CLASS[device_class], f"device descriptor class 0x{device_class:02X}"

    interfaces = payload.get("interfaceClasses")
    if isinstance(interfaces, list):
        for raw in interfaces[:MAX_INTERFACES]:
            code = _u8(raw)
            if code in USB_CLASS:
                return USB_CLASS[code], f"interface descriptor class 0x{code:02X}"

    if device_class:
        return "usbdevice", f"unrecognised class 0x{device_class:02X}"
    return "usbdevice", "no class declared"


def instance_id(payload: Mapping[str, Any]) -> str:
    """A stable identifier in the shape the Windows path would take.

    The serial number is used when the device publishes one.  When it does
    not -- most webcams do not -- the identifier falls back to a digest of the
    descriptor fields that do not change between page loads, so re-enrolling
    the same peripheral lands on the same twin instead of creating a second
    one.
    """
    vid = _u16(payload.get("vendorId"))
    pid = _u16(payload.get("productId"))
    serial = _text(payload.get("serialNumber"), 64)
    if serial:
        tail = re.sub(r"[^A-Za-z0-9]", "", serial)[:24] or "noserial"
    else:
        seed = "|".join((
            _text(payload.get("manufacturerName")),
            _text(payload.get("productName")),
            str(_u8(payload.get("deviceClass"))),
            str(_u8(payload.get("usbVersionMajor"))),
        ))
        tail = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"WEBUSB\\VID_{vid:04X}&PID_{pid:04X}\\{tail}"


def declared_power_w(payload: Mapping[str, Any]) -> Tuple[float, str]:
    """Bus power the configuration descriptor *permits*, never a measurement.

    ``MaxPower`` is reported by the browser in milliamps.  At the 5 V the bus
    supplies, the ceiling in watts follows directly -- but it remains an
    allowance the device declared, not current anybody observed, and the
    console labels it that way.
    """
    ma = payload.get("configurationMaxPowerMa")
    try:
        milliamps = float(ma)
    except (TypeError, ValueError):
        milliamps = 0.0
    if not 0.0 < milliamps <= 5000.0:
        return 0.0, "no usable MaxPower in the configuration descriptor"
    return round(milliamps * 5.0 / 1000.0, 3), (
        f"configuration descriptor MaxPower {milliamps:.0f} mA at 5 V")


def to_usb_device(payload: Mapping[str, Any]) -> UsbDevice:
    """Turn a validated browser payload into the object the pipeline expects.

    The result is an ordinary :class:`~cihdt.live.usb.UsbDevice`, so
    :class:`~cihdt.live.device.LiveDevice` and every stage above it work
    without knowing the descriptors arrived over HTTP rather than off a bus.
    """
    pnp_class, _why = classify(payload)
    vid = _u16(payload.get("vendorId"))
    pid = _u16(payload.get("productId"))

    name = (_text(payload.get("productName"))
            or _text(payload.get("manufacturerName"))
            or f"USB device {vid:04X}:{pid:04X}")

    now = time.time()
    return UsbDevice(
        instance_id=instance_id(payload),
        name=name,
        pnp_class=pnp_class,
        status="OK",                 # the browser only hands over a device it opened
        manufacturer=_text(payload.get("manufacturerName")),
        vid=f"{vid:04X}",
        pid=f"{pid:04X}",
        error_code=0,
        present=True,
        first_seen=now,
        present_since=now,
        last_seen=now,
    )


def describe(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """What the console shows about an enrolled device, and where it came from.

    Every entry is a descriptor the browser read, named so that a reviewer can
    check it against the device's own specification sheet.
    """
    pnp_class, why = classify(payload)
    power, power_note = declared_power_w(payload)
    vid = _u16(payload.get("vendorId"))
    pid = _u16(payload.get("productId"))
    major = _u8(payload.get("usbVersionMajor"))
    minor = _u8(payload.get("usbVersionMinor"))

    return {
        "vendor_id": f"0x{vid:04X}",
        "product_id": f"0x{pid:04X}",
        "manufacturer": _text(payload.get("manufacturerName")) or "(not published)",
        "product": _text(payload.get("productName")) or "(not published)",
        "serial": _text(payload.get("serialNumber"), 64) or "(not published)",
        "usb_version": f"{major}.{minor}" if major else "(not published)",
        "class": pnp_class,
        "class_source": why,
        "declared_power_w": power,
        "declared_power_note": power_note,
    }


# Where each of the sixteen features comes from once a device is enrolled this
# way.  The device half is genuinely the visitor's peripheral; the host half is
# the server the console runs on, and is labelled "server" rather than "host"
# so that no reading is mistaken for a measurement of the visitor's machine.
WEBUSB_PROVENANCE: Dict[str, Tuple[str, str]] = {
    "cpu_usage":         ("server", "psutil on the server, not your machine"),
    "mem_usage":         ("server", "psutil on the server, not your machine"),
    "net_in_kbps":       ("server", "server network counters"),
    "net_out_kbps":      ("server", "server network counters"),
    "packet_rate":       ("server", "server packet counters"),
    "conn_attempts":     ("server", "connections opened on the server"),
    "failed_logins":     ("unavailable",
                          "no unprivileged source on any host"),
    "unique_dst_ips":    ("server", "server connection table"),
    "port_diversity":    ("server", "server connection table"),
    "cmd_rate":          ("server", "server process-table growth"),
    "payload_entropy":   ("unavailable",
                          "payload inspection needs a capture the browser "
                          "cannot provide"),
    "avg_pkt_size":      ("server", "server byte and packet counters"),
    "session_duration":  ("device",
                          "seconds since you granted the page access"),
    "reconnects":        ("device",
                          "re-grants of access to this device in this session"),
    "device_event_rate": ("device",
                          "endpoint count from the configuration descriptor"),
    "power_draw":        ("declared",
                          "configuration descriptor MaxPower, an allowance "
                          "and not a measurement"),
}
