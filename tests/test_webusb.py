"""Enrolling a peripheral through the browser.

Two things are being protected here. The first is that a payload arriving
from a page is untrusted input and must survive hostile content without
passing any of it inward. The second is that a device enrolled this way is
indistinguishable to every stage above Step 1 from one read off the bus --
which is the module boundary the whole live/simulated substitution rests on.
"""
from __future__ import annotations

import json

import pytest

from cihdt.live import webusb
from cihdt.live.usb import UsbDevice
from cihdt.pipeline import Pipeline, StepError
from cihdt.server.pages import ACTIONS, _json_field

# A UVC webcam as Chrome reports it: composite, class 0xEF at the device
# level, the real class on the video interface, and no serial published.
WEBCAM = {
    "vendorId": 0x0C49, "productId": 0x636F,
    "deviceClass": 0xEF, "interfaceClasses": [0x0E, 0x01],
    "manufacturerName": "Generic", "productName": "USB 2.0 Camera",
    "serialNumber": None, "usbVersionMajor": 2, "usbVersionMinor": 0,
    "configurationMaxPowerMa": 500,
}
MOUSE = {
    "vendorId": 0x046D, "productId": 0xC077,
    "deviceClass": 0x00, "interfaceClasses": [0x03],
    "manufacturerName": "Logitech", "productName": "USB Optical Mouse",
    "usbVersionMajor": 2, "usbVersionMinor": 0,
    "configurationMaxPowerMa": 100,
}


# --------------------------------------------------------------- descriptors
def test_composite_device_is_classified_from_its_interfaces():
    """0xEF means 'ask the interfaces', and the video interface answers."""
    pnp_class, why = webusb.classify(WEBCAM)
    assert pnp_class == "camera"
    assert "interface descriptor" in why
    assert webusb.to_usb_device(WEBCAM).archetype == "smart_camera"


def test_device_level_class_is_used_when_it_is_meaningful():
    payload = dict(WEBCAM, deviceClass=0x0E, interfaceClasses=[])
    pnp_class, why = webusb.classify(payload)
    assert pnp_class == "camera"
    assert "device descriptor" in why


def test_unknown_class_does_not_masquerade_as_something_known():
    pnp_class, why = webusb.classify(
        {"deviceClass": 0x42, "interfaceClasses": []})
    assert pnp_class == "usbdevice"
    assert "unrecognised" in why


def test_identity_is_stable_across_page_loads():
    """Re-enrolling one peripheral must not produce a second twin."""
    assert webusb.instance_id(WEBCAM) == webusb.instance_id(dict(WEBCAM))


def test_distinct_devices_get_distinct_identities():
    assert webusb.instance_id(WEBCAM) != webusb.instance_id(MOUSE)
    assert (webusb.to_usb_device(WEBCAM).slug()
            != webusb.to_usb_device(MOUSE).slug())


def test_declared_power_is_derived_not_invented():
    watts, note = webusb.declared_power_w(WEBCAM)
    assert watts == pytest.approx(2.5)          # 500 mA at 5 V
    assert "MaxPower" in note

    # Absent or implausible, it is reported missing rather than guessed.
    for bad in (None, 0, -1, 1e9, "lots"):
        watts, note = webusb.declared_power_w(
            dict(WEBCAM, configurationMaxPowerMa=bad))
        assert watts == 0.0
        assert "no usable MaxPower" in note


def test_provenance_never_claims_the_visitors_machine():
    """Host telemetry comes from the server, and must say so.

    This is the assumption the report names in Section 8.2. It is acceptable
    only while it is stated, so the mapping is asserted rather than trusted.
    """
    kinds = {k: v[0] for k, v in webusb.WEBUSB_PROVENANCE.items()}
    assert kinds["cpu_usage"] == "server"
    assert kinds["power_draw"] == "declared"
    assert kinds["failed_logins"] == "unavailable"
    assert "host" not in set(kinds.values()), (
        "nothing may be attributed to the visitor's host")
    assert set(kinds) == set(
        __import__("cihdt.schemas", fromlist=["x"]).FEATURES)


# ------------------------------------------------------------- hostile input
@pytest.mark.parametrize("field,value", [
    ("manufacturerName", "A" * 10_000),
    ("productName", "<script>alert(1)</script>"),
    ("productName", "col\x00umn\x07bell\x1b[31m"),
    ("serialNumber", "../../../etc/passwd"),
    ("vendorId", 10 ** 9),
    ("vendorId", -1),
    ("deviceClass", {"not": "a number"}),
    ("interfaceClasses", list(range(5000))),
    ("configurationMaxPowerMa", float("nan")),
    ("productName", "=HYPERLINK(\"http://evil\",\"click\")"),
])
def test_hostile_descriptor_fields_are_neutralised(field, value):
    dev = webusb.to_usb_device(dict(WEBCAM, **{field: value}))
    assert len(dev.name) <= webusb.MAX_STR
    assert dev.name.isprintable()
    # No markup, and nothing a spreadsheet would evaluate on opening the
    # exported decision table.
    assert "<" not in dev.name and ">" not in dev.name
    assert not dev.name.startswith(("=", "+", "@"))
    assert len(dev.vid) == 4 and len(dev.pid) == 4
    int(dev.vid, 16), int(dev.pid, 16)          # parse or raise
    assert "\\" in dev.instance_id and dev.slug().startswith("usb_")


def test_payload_must_be_a_bounded_json_object():
    assert _json_field({"payload": json.dumps(WEBCAM)}, "payload")["vendorId"]
    for bad in ("", "{nope", "[1,2,3]", '"a string"', "null",
                json.dumps({"x": "A" * 9000})):
        with pytest.raises(StepError):
            _json_field({"payload": bad}, "payload")


# ------------------------------------------------------------------ pipeline
def test_browser_device_behaves_like_any_other_device():
    """Above Step 1 nothing may notice where the telemetry came from."""
    p = Pipeline()
    p.choose_source("webusb")
    assert p.is_live

    for payload in (WEBCAM, MOUSE):
        p.add_webusb_device(payload)
    assert len(p.fleet) == 2

    p.start_gateway()
    p.collect(ticks=40)
    p.create_twins()
    p.feed_twins()
    assert len(p.fit_predictors()["fitted"]) == 2
    assert len(p.generate_futures()["armed"]) == 2
    p.counterfactual_check()
    assert p.build_training_corpus()["corpus"]["rows"] > 0
    assert p.train_detector()["metrics"]["accuracy"] > 0.5


def test_the_same_peripheral_cannot_be_enrolled_twice():
    p = Pipeline()
    p.choose_source("webusb")
    p.add_webusb_device(WEBCAM)
    with pytest.raises(StepError, match="already being monitored"):
        p.add_webusb_device(WEBCAM)


def test_browser_enrolment_is_refused_outside_browser_mode():
    p = Pipeline()
    p.choose_source("simulated")
    with pytest.raises(StepError, match="browser-device mode"):
        p.add_webusb_device(WEBCAM)


def test_sources_cannot_be_mixed_once_a_fleet_exists():
    p = Pipeline()
    p.choose_source("webusb")
    p.add_webusb_device(WEBCAM)
    with pytest.raises(StepError, match="already been deployed"):
        p.choose_source("simulated")


def test_an_unknown_source_is_rejected():
    with pytest.raises(StepError):
        Pipeline().choose_source("telepathy")


def test_the_form_action_reaches_the_pipeline():
    p = Pipeline()
    p.choose_source("webusb")
    result = ACTIONS["0/webusb"](p, {"payload": json.dumps(WEBCAM)})
    assert result["device"]["device_type"] == "smart_camera"
    assert result["descriptor"]["vendor_id"] == "0x0C49"
    assert result["descriptor"]["declared_power_w"] == pytest.approx(2.5)


def test_a_device_type_override_must_be_a_real_type():
    p = Pipeline()
    p.choose_source("webusb")
    with pytest.raises(StepError, match="Device type"):
        p.add_webusb_device(WEBCAM, device_type="toaster")


def test_resulting_object_is_an_ordinary_usb_device():
    """The seam the substitution depends on: the type must not be special."""
    assert type(webusb.to_usb_device(WEBCAM)) is UsbDevice
