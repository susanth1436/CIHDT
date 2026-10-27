"""The manual pipeline and its HTTP surface.

The point of these tests is the *manual* contract: nothing may happen that the
operator did not ask for, and nothing may be attempted out of order.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from cihdt.config import SETTINGS
from cihdt.pipeline import Pipeline, StepError


def build_fleet(p: Pipeline) -> Pipeline:
    for dtype, count in [("smart_camera", 2), ("smart_bulb", 1),
                         ("smart_lock", 1), ("temperature_sensor", 1)]:
        for _ in range(count):
            p.add_device(dtype)
    return p


@pytest.fixture
def ready(tmp_path, monkeypatch):
    """A pipeline warmed through Step 5, with an isolated model registry."""
    import cihdt.pipeline as mod
    monkeypatch.setattr(mod, "MODEL_DIR", tmp_path / "models")
    p = build_fleet(Pipeline(seed=21))
    p.start_gateway()
    p.collect(45)
    p.create_twins()
    p.feed_twins()
    p.fit_predictors()
    p.generate_futures()
    p.counterfactual_check()
    return p


# ------------------------------------------------------------ step gating ---
def test_steps_start_locked_and_unlock_in_order():
    p = Pipeline(seed=1)
    status = {s["id"]: s["status"] for s in p.steps()}
    assert status[1] == "ready"
    assert status[2] == "locked"
    assert status[8] == "locked"

    build_fleet(p)
    assert {s["id"]: s["status"] for s in p.steps()}[1] == "done"
    assert {s["id"]: s["status"] for s in p.steps()}[2] == "ready"


def test_out_of_order_steps_name_the_blocking_step():
    p = Pipeline(seed=1)
    with pytest.raises(StepError) as exc:
        p.start_gateway()
    assert exc.value.required_step == 1

    build_fleet(p)
    with pytest.raises(StepError) as exc:
        p.fit_predictors()
    assert exc.value.required_step == 3


def test_gateway_needs_two_devices():
    p = Pipeline(seed=1)
    p.add_device("smart_bulb")
    with pytest.raises(StepError, match="at least two"):
        p.start_gateway()


def test_nothing_advances_without_being_asked():
    """The manual contract: only an explicit request may advance the fleet."""
    p = build_fleet(Pipeline(seed=1))
    assert p.stats["ticks"] == 0                 # adding devices does not tick
    p.start_gateway()
    assert p.stats["ticks"] == 0                 # nor does starting the gateway
    p.collect(3)
    assert p.stats["ticks"] == 3                 # only collect() does
    p.create_twins()
    p.feed_twins()
    assert p.stats["ticks"] == 3                 # nor do the twin steps


def test_collect_buffers_until_the_twins_are_fed(ready):
    p = ready
    p.collect(10)
    before = p.twins.get("smart_camera_01").observations
    assert len(p.buffer) == 10
    p.feed_twins()
    assert len(p.buffer) == 0
    assert p.twins.get("smart_camera_01").observations > before


def test_futures_must_exist_before_scoring():
    p = build_fleet(Pipeline(seed=2))
    p.start_gateway()
    p.collect(45)
    p.create_twins()
    p.feed_twins()
    p.fit_predictors()
    with pytest.raises(StepError) as exc:
        p.counterfactual_check()
    assert exc.value.required_step == 5


# ------------------------------------------------------- detection flow ----
def test_detector_flow_and_manual_attack(ready):
    p = ready
    p.build_training_corpus(200)
    result = p.train_detector()
    assert result["metrics"]["accuracy"] > 0.85
    assert p.detector is not None

    assert p.fleet.get("smart_camera_01").is_compromised is False
    p.launch_attack("smart_camera_01", "ddos", duration=10, intensity=1.0)
    assert p.fleet.get("smart_camera_01").is_compromised is True

    out = p.monitor(ticks=4)
    rows = [r for r in out["all_rows"] if r["device_id"] == "smart_camera_01"]
    assert any(r["predicted"] != "normal" for r in rows)


def test_unknown_device_and_attack_are_rejected(ready):
    with pytest.raises(StepError):
        ready.launch_attack("nope", "ddos")
    with pytest.raises(StepError):
        ready.launch_attack("smart_camera_01", "not_an_attack")


# ----------------------------------------------- craft / validate / apply ---
def test_crafting_does_not_apply_anything(ready):
    p = ready
    p.build_training_corpus(200)
    p.train_detector()
    pool_before = p.retrainer.pool_size

    p.craft_update("label_flip", rows=200)
    assert len(p.inbox) == 1
    item = next(iter(p.inbox.values()))
    assert item["state"] == "pending"
    assert item["report"] is None
    # Nothing has touched the pool or the quarantine.
    assert p.retrainer.pool_size == pool_before
    assert p.quarantine.total_quarantined == 0


def test_validation_does_not_route_until_applied(ready):
    p = ready
    p.build_training_corpus(200)
    p.train_detector()
    p.refresh_bank()
    p.calibrate_gate(4)

    uid = p.craft_update("label_flip", rows=200)["created"][0]["update_id"]
    report = p.validate_update(uid)["report"]
    assert report["decision"] == "QUARANTINED"
    assert p.quarantine.total_quarantined == 0     # still not routed

    p.apply_decision(uid)
    assert p.quarantine.total_quarantined == 1


def test_applying_twice_is_refused(ready):
    p = ready
    p.build_training_corpus(200)
    p.train_detector()
    p.refresh_bank()
    p.calibrate_gate(4)
    uid = p.craft_update("clean", rows=200)["created"][0]["update_id"]
    p.validate_update(uid)
    p.apply_decision(uid)
    with pytest.raises(StepError, match="already been applied"):
        p.apply_decision(uid)


def test_operator_can_override_the_gate(ready):
    p = ready
    p.build_training_corpus(200)
    p.train_detector()
    p.refresh_bank()
    p.calibrate_gate(4)

    uid = p.craft_update("label_flip", rows=200)["created"][0]["update_id"]
    p.validate_update(uid)
    result = p.apply_decision(uid, override="ACCEPTED")
    assert result["overridden"] is True
    assert result["decision"] == "ACCEPTED"
    assert p.stats["overrides"] == 1
    # And the override is on the record.
    assert any("overrode" in e["message"] for e in p.events)


def test_apply_requires_validation_first(ready):
    p = ready
    p.build_training_corpus(200)
    p.train_detector()
    uid = p.craft_update("clean", rows=200)["created"][0]["update_id"]
    with pytest.raises(StepError, match="Validate"):
        p.apply_decision(uid)


# ------------------------------------------------------------ HTTP layer ----
TEST_EMAIL = "tester@example.com"
TEST_PASSWORD = "test-operator-password"


@pytest.fixture
def anon(tmp_path, monkeypatch):
    """A client with no session, on an isolated account store."""
    from cihdt.server import api, auth, pages
    import cihdt.pipeline as mod
    monkeypatch.setattr(mod, "MODEL_DIR", tmp_path / "models")

    # Never touch the real database from a test run.
    from cihdt.server import db as dbmod
    database = dbmod.Database(tmp_path / "test.sqlite3")
    monkeypatch.setattr(dbmod, "DB", database)

    store = auth.UserStore(database=database,
                           legacy_path=tmp_path / "absent.json")
    store.add_user(TEST_EMAIL, TEST_PASSWORD, "Tester")
    # The store bootstraps an account when it finds none; drop it so a test
    # starts from exactly one known account.
    database.execute("DELETE FROM users WHERE email != ?", (TEST_EMAIL,))
    monkeypatch.setattr(auth, "USERS", store)
    monkeypatch.setattr(auth, "SESSIONS", auth.SessionStore(database))

    api.PIPELINE = Pipeline(seed=31)
    pages.reset_view()          # the pages remember results between requests
    return TestClient(api.app)


@pytest.fixture
def client(anon):
    """A signed-in client. Everything behind the gate needs one."""
    r = anon.post("/login", data={"email": TEST_EMAIL,
                                  "password": TEST_PASSWORD},
                  follow_redirects=False)
    assert r.status_code == 303, "fixture could not sign in"
    return anon


def test_catalogue_exposes_devices_and_strategies(client):
    body = client.get("/api/catalogue").json()
    assert len(body["devices"]) == 6
    assert {d["type"] for d in body["devices"]} >= {"smart_camera", "smart_bulb"}
    assert len(body["steps"]) == 12
    weights = body["config"]["validate"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_every_action_returns_the_full_state(client):
    body = client.post("/api/step1/add", json={"device_type": "smart_camera"}).json()
    assert "result" in body and "state" in body
    assert body["state"]["fleet"]["n_devices"] == 1


def test_out_of_order_request_returns_409_with_the_blocking_step(client):
    r = client.post("/api/step2/start")
    assert r.status_code == 409
    assert r.json()["detail"]["required_step"] == 1


def test_bad_input_is_rejected_by_validation(client):
    r = client.post("/api/step2/collect", json={"ticks": 99999})
    assert r.status_code == 422


def test_reset_returns_to_an_empty_step_one(client):
    client.post("/api/step1/add", json={"device_type": "smart_camera"})
    client.post("/api/step1/add", json={"device_type": "smart_bulb"})
    assert client.get("/api/state").json()["fleet"]["n_devices"] == 2

    client.post("/api/reset")
    state = client.get("/api/state").json()
    assert state["fleet"]["n_devices"] == 0
    assert state["steps"][0]["status"] == "ready"
    assert state["steps"][1]["status"] == "locked"


# ------------------------------------------------- the multi-page console ---
# The console is server-rendered: one URL per step, one full page load per
# action, and no JavaScript at all.  These tests hold that shape in place.
def test_root_is_a_landing_page_listing_the_twelve_steps(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text
    # With no source chosen yet, the front door sends you to that choice.
    assert "choose a source" in r.text
    assert "/start" in r.text
    # Every step is named and linked from the front door.
    for step in range(1, 13):
        assert f"{step:02d}." in r.text
    assert "THE TWELVE" in r.text


def test_live_source_can_be_chosen_and_lists_real_devices(client):
    """Step 0: the choice before Step 1, and what live mode discloses."""
    page = client.get("/start")
    assert page.status_code == 200
    assert "Simulated fleet" in page.text and "Live USB devices" in page.text
    # The provenance of every feature is disclosed, not glossed over.
    assert "failed_logins" in page.text
    assert "unavailable" in page.text

    # Step 1 will not deploy anything until a source exists.
    assert "Choose a telemetry source first" in client.get("/step/1").text

    client.post("/step/0/source", data={"mode": "simulated"})
    assert "Device catalogue" in client.get("/step/1").text


def test_usb_slug_separates_the_interfaces_of_one_device():
    """A composite peripheral enumerates once per interface.

    A webcam with a microphone appears as MI_00 for video and MI_02 for audio.
    Those entries share a VID, a PID and a trailing instance segment, so an id
    built from the tail collides and the second one cannot be enrolled.
    """
    from cihdt.live.usb import UsbDevice

    video = UsbDevice(
        instance_id=r"USB\VID_0C49&PID_636F&MI_00\6&19C24A44&0&0000",
        name="USB 2.0 Camera", pnp_class="Camera", status="OK",
        vid="0C49", pid="636F")
    audio = UsbDevice(
        instance_id=r"USB\VID_0C49&PID_636F&MI_02\6&19C24A44&0&0002",
        name="USB 2.0 Camera", pnp_class="MEDIA", status="OK",
        vid="0C49", pid="636F")

    assert video.slug() != audio.slug()
    assert video.slug() == video.slug()          # stable across calls
    # Windows puts '&' in instance ids; it must not reach a URL.
    for dev in (video, audio):
        assert re.fullmatch(r"[a-z0-9_]+", dev.slug()), dev.slug()
        assert "0c49" in dev.slug() and "636f" in dev.slug()


def test_live_mode_refuses_simulated_devices(client):
    """The two sources cannot be mixed in one fleet."""
    from cihdt.server import api
    if not api.PIPELINE.live_support()["available"]:
        pytest.skip("live sampling is unavailable on this host")
    client.post("/step/0/source", data={"mode": "live"})
    page = client.post("/step/1/add", data={"device_type": "smart_bulb"})
    assert "Cannot do that yet" in page.text
    assert "live mode" in page.text
    assert api.PIPELINE.fleet.devices == {}


def test_a_step_page_shows_only_that_step(client):
    """No rail of all twelve: a page listing the others is a control panel."""
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})
    page = client.get("/step/1")
    # Its own title and purpose are present...
    assert "Create the IoT environment" in page.text
    # ...but the other steps' titles are not listed on it.
    for other in ("Predict future states", "Simulate model poisoning",
                  "Quarantine and analysis", "Self-healing"):
        assert other not in page.text, other


def test_finishing_a_step_offers_the_next_one(client):
    """An unfinished step shows the next one locked; a finished one opens it."""
    page = client.get("/step/1")                      # no devices yet
    assert "is not finished yet" in page.text
    assert "IS LOCKED" in page.text
    assert "href='/step/2'" not in page.text

    client.post("/step/1/add", data={"device_type": "smart_camera"})
    page = client.get("/step/1")
    assert "Step 1 complete" in page.text
    assert "Continue to Step 2" in page.text
    assert "href='/step/2'" in page.text


def test_step_pages_are_real_pages_not_one_app_shell(client):
    """Each step must be its own document, titled with that step."""
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})

    one = client.get("/step/1")
    assert one.status_code == 200
    assert "<!DOCTYPE html>" in one.text
    assert "<title>Create the IoT environment &middot; CIHDT</title>" in one.text
    assert "Step 01 of 12" in one.text

    two = client.get("/step/2")
    assert two.status_code == 200
    assert "<title>Start the edge gateway &middot; CIHDT</title>" in two.text
    assert "Step 02 of 12" in two.text
    # Two genuinely different documents, not one shell swapping its contents.
    assert one.text != two.text


def test_no_javascript_is_served(client):
    page = client.get("/step/1")
    assert "<script" not in page.text.lower()
    assert client.get("/static/app.js").status_code == 404
    assert client.get("/static/styles.css").status_code == 200


def test_every_step_has_its_own_url(client):
    for step in range(1, 13):
        r = client.get(f"/step/{step}")
        assert r.status_code == 200, step
        assert f"Step {step} of 12" in r.text
    assert client.get("/step/0").status_code == 404
    assert client.get("/step/13").status_code == 404


def test_locked_step_explains_itself_instead_of_rendering_controls(client):
    page = client.get("/step/8")
    assert "This step is locked" in page.text
    assert "Craft a hostile training contribution" not in page.text


def test_action_redirects_so_a_refresh_does_not_repeat_it(client):
    """Post/Redirect/Get: the manual contract depends on this."""
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})

    r = client.post("/step/2/start", data={}, follow_redirects=False)
    assert r.status_code == 303
    # The fragment lands the operator back on the panel they pressed.
    assert r.headers["location"] == "/step/2#edge-gateway"

    r = client.post("/step/2/collect", data={"ticks": 3},
                    follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api/state").json()["stats"]["ticks"] == 3

    # Re-reading the page must not collect another tick.
    client.get("/step/2")
    client.get("/step/2")
    assert client.get("/api/state").json()["stats"]["ticks"] == 3


def test_an_action_returns_to_its_own_panel_not_the_top_of_the_page(client):
    """Every action is a full page load, so it has to land somewhere.

    Without a fragment the browser drops the operator back at the top after
    each click, which on a long step page means losing their place entirely.
    """
    from cihdt.server import pages

    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})
    client.post("/step/2/start", data={})

    r = client.post("/step/2/collect", data={"ticks": 3},
                    follow_redirects=False)
    assert r.headers["location"] == "/step/2#collect-telemetry"

    # And the id it points at must actually exist, or the browser silently
    # falls back to the top and the bug is back.
    assert "id='collect-telemetry'" in client.get("/step/2").text


def test_every_anchored_action_points_at_a_real_panel(client):
    """A fragment with no matching id is indistinguishable from no fragment."""
    from cihdt.server import pages

    # Only the panels reachable without running the whole pipeline are checked
    # here; the rest are covered by the walkthrough.
    reachable = {
        "1/add": ("/step/1", "device-catalogue"),
        "2/start": ("/step/2", "edge-gateway"),
        "2/collect": ("/step/2", "collect-telemetry"),
        "3/create": ("/step/3", "create-and-feed-twins"),
        "4/fit": ("/step/4", "fit-the-forward-models"),
    }
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})
    client.post("/step/2/start", data={})
    client.post("/step/2/collect", data={"ticks": 40})
    client.post("/step/3/create", data={})
    client.post("/step/3/feed", data={})

    for action, (url, frag) in reachable.items():
        assert pages.ANCHORS[action] == frag, action
        assert f"id='{frag}'" in client.get(url).text, frag


def test_no_post_redirects_without_a_fragment(client):
    """A bare redirect drops the operator at the top of the page.

    This caught three regressions once already: the account forms, the
    refused-action path, and the step-0 source choice were all added after the
    anchors went in and all landed back at the top.
    """
    from cihdt.server import pages

    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})

    posts = [
        ("/step/1/add", {"device_type": "smart_plug"}),
        ("/step/2/start", {}),
        ("/step/2/collect", {"ticks": 3}),
        ("/accounts/add", {"email": "x@y.com", "password": "another-pass"}),
        ("/accounts/password", {"email": "x@y.com", "password": "new-pass123"}),
        ("/accounts/remove", {"email": "x@y.com"}),
    ]
    for path, data in posts:
        r = client.post(path, data=data, follow_redirects=False)
        assert r.status_code == 303, path
        loc = r.headers["location"]
        assert "#" in loc, f"{path} redirects to {loc} with no fragment"
        page, frag = loc.split("#", 1)
        assert f"id='{frag}'" in client.get(page).text,             f"{path} points at #{frag}, which is not on {page}"


def test_a_refused_action_also_returns_to_its_control(client):
    """Being refused must not cost the operator their place as well."""
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})

    # Step 2 is unlocked, but collecting before the gateway starts is refused.
    r = client.post("/step/2/collect", data={"ticks": 5},
                    follow_redirects=False)
    assert r.headers["location"] == "/step/2#collect-telemetry"

    page = client.get("/step/2")
    assert "Cannot do that yet" in page.text
    assert "id='collect-telemetry'" in page.text


def test_nothing_is_pinned_wider_than_a_phone(client):
    """Guard the CSS rules that stop one long value widening the whole page.

    Three regressions found their way in this way: the top bar grew to eight
    items and would not wrap, the activity page prints a Windows file path
    with nothing to break at, and a locked step offers a button whose label
    is a whole sentence. Each one dragged every page wider than the screen.
    """
    css = client.get("/static/styles.css").text

    def rule(selector):
        start = css.index(selector)
        return css[start:css.index("}", start)]

    assert "flex-wrap: wrap" in rule(".nav nav {")
    assert "overflow-wrap: anywhere" in rule(".kv dd {")
    # Long labels must be allowed to wrap on a narrow screen.
    narrow = css[css.index("@media (max-width: 920px)"):]
    assert "white-space: normal" in narrow


def test_the_error_banner_travels_with_the_operator(client):
    """It is sticky, so a refusal stays readable from down the page."""
    css = client.get("/static/styles.css").text
    start = css.index(".flash {")
    flash = css[start:css.index("}", start)]
    assert "position: sticky" in flash


def test_out_of_order_action_flashes_the_blocking_step(client):
    r = client.post("/step/2/start", data={})
    assert r.status_code == 200                 # redirected back to the page
    assert "Cannot do that yet" in r.text
    assert "Go to Step 1" in r.text
    # And nothing was started.
    assert client.get("/api/state").json()["gateway"]["online"] is False


def test_unknown_action_is_a_404(client):
    assert client.post("/step/1/teleport", data={}).status_code == 404


def test_typed_values_are_remembered_on_the_next_render(client):
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})
    client.post("/step/2/start", data={})
    client.post("/step/2/collect", data={"ticks": 7})
    assert "value='7'" in client.get("/step/2").text


def test_reset_asks_before_discarding(client):
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    confirm = client.get("/reset")
    assert confirm.status_code == 200
    assert "Discard this session" in confirm.text
    # Asking did not reset anything.
    assert client.get("/api/state").json()["fleet"]["n_devices"] == 1

    done = client.post("/reset", follow_redirects=False)
    assert done.status_code == 303
    assert done.headers["location"] == "/step/1"
    assert client.get("/api/state").json()["fleet"]["n_devices"] == 0


def test_pages_render_the_same_explanation_the_api_returns(client):
    """One source of truth for the prose, shared with the terminal front end."""
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    page = client.post("/step/1/add", data={"device_type": "smart_bulb"})
    assert "What just happened" in page.text
    assert "Network now has 2 devices." in page.text
    assert "Explanation unavailable" not in page.text


def test_page_html_escapes_untrusted_values(client):
    """Device ids and sources reach the page as text, never as markup."""
    from cihdt.server import html as H
    assert H.esc("<script>alert(1)</script>") == \
        "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert H.esc("a'b\"c&d") == "a&#39;b&quot;c&amp;d"
    assert "<b>" not in H.badge("<b>x</b>")


# ------------------------------------------------------ post-run explanations
EXPLAINED_ACTIONS = [
    "add_device", "start_gateway", "collect", "create_twins", "feed_twins",
    "fit_predictors", "generate_futures", "counterfactual_check",
    "build_corpus", "train_detector", "launch_attack", "monitor",
    "craft_update", "refresh_bank", "calibrate_gate", "validate_update",
    "apply_decision", "generate_vaccine", "measure_resistance", "analyse",
    "rescore", "release", "retrain", "health_check", "self_heal", "rollback",
]


def _assert_well_formed(card, action):
    assert card, f"{action} produced no explanation"
    for field in ("headline", "what_happened", "reading", "why_it_matters",
                  "next", "tone"):
        assert field in card, f"{action} explanation missing {field}"
    assert card["headline"], f"{action} headline is empty"
    assert card["tone"] in ("info", "good", "warn", "bad")
    assert all(isinstance(b, str) and b.strip() for b in card["what_happened"])
    for r in card["reading"]:
        assert {"label", "value", "note"} <= set(r)
    assert "Explanation unavailable" not in card["headline"], \
        f"{action} explanation raised: {card['what_happened']}"


def test_every_action_explains_itself(ready):
    """Each operator action must return a well-formed explanation."""
    p = ready
    seen = {}

    seen["add_device"] = p.add_device("smart_plug")["explanation"]
    # The fixture already started the gateway, so exercise that one on a fresh
    # pipeline rather than stubbing it.
    fresh = build_fleet(Pipeline(seed=77))
    seen["start_gateway"] = fresh.start_gateway()["explanation"]
    seen["collect"] = p.collect(4)["explanation"]
    seen["create_twins"] = p.create_twins()["explanation"]
    seen["feed_twins"] = p.feed_twins()["explanation"]
    seen["fit_predictors"] = p.fit_predictors()["explanation"]
    seen["generate_futures"] = p.generate_futures()["explanation"]
    seen["counterfactual_check"] = p.counterfactual_check()["explanation"]
    seen["build_corpus"] = p.build_training_corpus(200)["explanation"]
    seen["train_detector"] = p.train_detector()["explanation"]
    seen["launch_attack"] = p.launch_attack(
        "smart_camera_01", "ddos", 8, 1.0)["explanation"]
    seen["monitor"] = p.monitor(2)["explanation"]
    seen["refresh_bank"] = p.refresh_bank()["explanation"]
    seen["calibrate_gate"] = p.calibrate_gate(3)["explanation"]

    uid = p.craft_update("label_flip", rows=200)
    seen["craft_update"] = uid["explanation"]
    update_id = uid["created"][0]["update_id"]
    seen["validate_update"] = p.validate_update(update_id)["explanation"]
    seen["apply_decision"] = p.apply_decision(update_id)["explanation"]

    seen["generate_vaccine"] = p.generate_vaccine()["explanation"]
    seen["measure_resistance"] = p.measure_resistance()["explanation"]
    seen["analyse"] = p.analyse_quarantined(update_id)["explanation"]
    seen["rescore"] = p.rescore_quarantine()["explanation"]
    seen["release"] = p.release_quarantined(update_id)["explanation"]
    seen["retrain"] = p.retrain(immunize=False)["explanation"]
    seen["health_check"] = p.health_check()["explanation"]
    seen["self_heal"] = p.self_heal("test", retrain_after=False)["explanation"]

    for action, card in seen.items():
        _assert_well_formed(card, action)


def test_explanations_are_derived_not_boilerplate(ready):
    """The text must quote the numbers the step actually produced."""
    p = ready
    p.build_training_corpus(200)
    card = p.train_detector()["explanation"]
    blob = " ".join(card["what_happened"])
    assert "recall" in blob                        # names the weakest class
    values = {r["label"]: r["value"] for r in card["reading"]}
    assert values["Accuracy"].endswith("%")
    assert values["False negatives"] != values["Accuracy"]

    # A different fleet state must produce different text.
    p.refresh_bank()
    p.calibrate_gate(3)
    uid = p.craft_update("clean", rows=200)["created"][0]["update_id"]
    clean_card = p.validate_update(uid)["explanation"]
    assert clean_card["tone"] == "good"
    assert "Accepted" in clean_card["headline"]

    uid2 = p.craft_update("label_flip", rows=200)["created"][0]["update_id"]
    poison_card = p.validate_update(uid2)["explanation"]
    assert "Quarantined" in poison_card["headline"]
    assert poison_card["headline"] != clean_card["headline"]


def test_explanation_failure_never_breaks_the_action():
    """A broken explainer must not take the step down with it."""
    from cihdt import explain as explain_mod

    def boom(res, p):
        raise ValueError("deliberate")

    original = explain_mod.EXPLAINERS["collect"]
    explain_mod.EXPLAINERS["collect"] = boom
    try:
        p = build_fleet(Pipeline(seed=3))
        p.start_gateway()
        result = p.collect(2)
        assert result["ticks_collected"] == 2          # the action still worked
        assert "Explanation unavailable" in result["explanation"]["headline"]
    finally:
        explain_mod.EXPLAINERS["collect"] = original


def test_api_returns_explanations(client):
    client.post("/api/step1/add", json={"device_type": "smart_camera"})
    body = client.post("/api/step1/add",
                       json={"device_type": "smart_bulb"}).json()
    card = body["result"]["explanation"]
    _assert_well_formed(card, "add_device")
    assert card["next_step"] == 2

    body = client.post("/api/step2/start").json()
    assert "explanation" in body["result"]


# ------------------------------------------------------------------ access ---
def test_everything_is_behind_the_gate(anon):
    """A login page that guards only the HTML guards nothing."""
    for path in ("/", "/start", "/step/1", "/accounts", "/reset"):
        r = anon.get(path, follow_redirects=False)
        assert r.status_code == 303, path
        assert r.headers["location"].startswith("/login?next="), path

    # The JSON surface is the same console; it is gated too.
    for path in ("/api/state", "/api/catalogue"):
        assert anon.get(path).status_code == 401, path
    assert anon.post("/api/step1/add",
                     json={"device_type": "smart_camera"}).status_code == 401
    blocked = anon.post("/step/1/add", data={"device_type": "smart_camera"},
                        follow_redirects=False)
    assert blocked.status_code == 303
    assert blocked.headers["location"].startswith("/login")
    # And nothing happened.
    assert anon.post("/login", data={"email": TEST_EMAIL,
                                     "password": TEST_PASSWORD})
    assert anon.get("/api/state").json()["fleet"]["n_devices"] == 0


def test_login_page_is_reachable_without_a_session(anon):
    r = anon.get("/login")
    assert r.status_code == 200
    assert "type='password'" in r.text
    assert "SIGN IN" in r.text
    # Signed out, there is nothing to navigate to but the way in.
    assert "/step/1" not in r.text
    assert anon.get("/static/styles.css").status_code == 200


def test_wrong_password_is_refused_and_says_nothing_useful(anon):
    r = anon.post("/login", data={"email": TEST_EMAIL, "password": "wrong"})
    assert r.status_code == 401
    assert "not recognised" in r.text

    # A missing account must give the same answer, or accounts can be probed.
    r2 = anon.post("/login", data={"email": "ghost@example.com", "password": "wrong"})
    assert r2.status_code == 401
    assert "not recognised" in r2.text


def test_signing_in_and_out(anon):
    r = anon.post("/login", data={"email": TEST_EMAIL,
                                  "password": TEST_PASSWORD},
                  follow_redirects=False)
    assert r.status_code == 303
    cookie = r.cookies.get("cihdt_session")
    assert cookie, "no session cookie issued"

    page = anon.get("/step/1")
    assert page.status_code == 200
    assert "Tester" in page.text and "Sign out" in page.text

    anon.post("/logout", follow_redirects=False)
    assert anon.get("/step/1", follow_redirects=False).status_code == 303


def test_sign_in_returns_you_to_where_you_were_going(anon):
    r = anon.get("/step/5", follow_redirects=False)
    assert r.headers["location"] == "/login?next=/step/5"
    r = anon.post("/login", data={"email": TEST_EMAIL,
                                  "password": TEST_PASSWORD,
                                  "next": "/step/5"}, follow_redirects=False)
    assert r.headers["location"] == "/step/5"


def test_next_cannot_be_used_to_bounce_offsite(anon):
    """An open redirect would make a crafted sign-in link look trustworthy."""
    for hostile in ("https://evil.example/x", "//evil.example/x"):
        r = anon.post("/login", data={"email": TEST_EMAIL,
                                      "password": TEST_PASSWORD,
                                      "next": hostile},
                      follow_redirects=False)
        assert r.headers["location"] == "/", hostile
        anon.post("/logout")


def test_passwords_are_never_stored_in_the_clear(tmp_path):
    from cihdt.server import auth, db as dbmod
    database = dbmod.Database(tmp_path / "t.sqlite3")
    store = auth.UserStore(database=database,
                           legacy_path=tmp_path / "absent.json")
    store.add_user("alice@example.com", "a-long-enough-password", "Alice")

    # Writes sit in the write-ahead log until checkpointed, so fold them into
    # the main file before reading it, or this would pass vacuously.
    database.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = (tmp_path / "t.sqlite3").read_bytes()
    assert b"pbkdf2_sha256$" in raw, "hash was not written"
    assert b"a-long-enough-password" not in raw
    assert store.authenticate("alice@example.com",
                              "a-long-enough-password") is not None
    assert store.authenticate("alice@example.com", "wrong") is None
    # The same password hashes differently each time: the salt is per user.
    assert auth.hash_password("x") != auth.hash_password("x")


def test_repeated_failures_pause_the_account(tmp_path):
    from cihdt.server import auth, db as dbmod
    store = auth.UserStore(database=dbmod.Database(tmp_path / "t.sqlite3"),
                           legacy_path=tmp_path / "absent.json")
    store.add_user("bob@example.com", "a-long-enough-password")
    for _ in range(5):
        assert store.authenticate("bob@example.com", "wrong") is None
    assert store.locked_for("bob@example.com") > 0
    # Even the right password waits out the pause.
    assert store.authenticate("bob@example.com",
                              "a-long-enough-password") is None


def test_accounts_can_be_added_and_the_last_one_kept(client):
    page = client.post("/accounts/add",
                       data={"email": "second@example.com",
                             "password": "another-pass",
                             "display_name": "Second"})
    assert "second@example.com" in page.text

    from cihdt.server import auth
    assert auth.USERS.count == 2
    client.post("/accounts/remove", data={"email": "second@example.com"})
    assert auth.USERS.count == 1

    # Removing the last account would lock everyone out.
    page = client.post("/accounts/remove", data={"email": TEST_EMAIL})
    assert auth.USERS.count == 1
    assert "only account" in page.text or "Cannot do that yet" in page.text


# ---------------------------------------------------------------- database ---
def test_schema_is_versioned_and_migration_is_idempotent(tmp_path):
    from cihdt.server import db as dbmod
    database = dbmod.Database(tmp_path / "m.sqlite3")
    assert database.migrate() == dbmod.SCHEMA_VERSION
    assert database.migrate() == dbmod.SCHEMA_VERSION      # safe to re-run
    stats = database.stats()
    assert stats["journal_mode"] == "wal"
    assert stats["schema_version"] == dbmod.SCHEMA_VERSION


def test_foreign_keys_are_enforced_and_cascade(tmp_path):
    """SQLite ignores foreign keys unless asked, so this must be checked."""
    import sqlite3
    from cihdt.server import db as dbmod
    database = dbmod.Database(tmp_path / "fk.sqlite3")
    database.execute("INSERT INTO users (email, password_hash, created_at)"
                     " VALUES (?,?,?)", ("al@x.co", "h", 1.0))

    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO sessions (token, email, created_at, last_seen)"
            " VALUES (?,?,?,?)", ("t", "ghost@x.co", 1.0, 1.0))

    database.execute(
        "INSERT INTO sessions (token, email, created_at, last_seen)"
        " VALUES (?,?,?,?)", ("t", "al@x.co", 1.0, 1.0))
    database.execute("DELETE FROM users WHERE email = ?", ("al@x.co",))
    assert database.query("SELECT * FROM sessions") == []


def test_removing_an_account_ends_its_sessions(client, tmp_path):
    """A removed operator must not keep a live console."""
    from cihdt.server import auth
    auth.USERS.add_user("temp@example.com", "a-long-enough-password", "Temp")
    token = auth.SESSIONS.create("temp@example.com")
    assert auth.SESSIONS.resolve(token) == "temp@example.com"

    client.post("/accounts/remove", data={"email": "temp@example.com"})
    assert auth.SESSIONS.resolve(token) is None


def test_sessions_outlive_a_restart(tmp_path):
    """Sessions live in the database, not in a dict that a restart clears."""
    from cihdt.server import auth, db as dbmod
    path = tmp_path / "s.sqlite3"
    store = auth.UserStore(database=dbmod.Database(path),
                           legacy_path=tmp_path / "absent.json")
    store.add_user("carol@example.com", "a-long-enough-password")
    token = auth.SessionStore(dbmod.Database(path)).create("carol@example.com")

    # A new process would open the same file and find the session intact.
    reopened = auth.SessionStore(dbmod.Database(path))
    assert reopened.resolve(token) == "carol@example.com"


def test_every_action_is_audited(client):
    from cihdt.server import db as dbmod
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/2/start", data={})          # refused: needs two devices

    entries = dbmod.recent(dbmod.DB, limit=50)
    actions = {e["action"]: e for e in entries}
    assert "login" in actions and actions["login"]["outcome"] == "ok"
    assert "step1/add" in actions
    # A blocked attempt is recorded too, with why.
    refused = [e for e in entries if e["outcome"] == "refused"]
    assert refused and "step2/start" in {e["action"] for e in refused}
    assert all(e["actor"] == TEST_EMAIL for e in entries
               if e["action"].startswith("step"))


def test_failed_sign_in_is_audited(anon):
    from cihdt.server import db as dbmod
    anon.post("/login", data={"email": TEST_EMAIL, "password": "wrong"})
    entries = dbmod.recent(dbmod.DB, limit=10)
    assert any(e["action"] == "login" and e["outcome"] == "refused"
               for e in entries)


def test_activity_page_shows_the_trail(client):
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    page = client.get("/activity")
    assert page.status_code == 200
    assert "Audit trail" in page.text
    assert "step1/add" in page.text
    assert "SQLite" in page.text
    # A full session token must never be rendered.
    assert "Open sessions" in page.text


def test_audit_values_are_parameterised_not_interpolated(tmp_path):
    """A hostile detail string is data, never SQL."""
    from cihdt.server import db as dbmod
    database = dbmod.Database(tmp_path / "inj.sqlite3")
    database.execute("INSERT INTO users (email, password_hash, created_at)"
                     " VALUES (?,?,?)", ("al@x.co", "h", 1.0))
    dbmod.record(database, "al@x.co", "login", "'; DROP TABLE users; --")
    assert database.query_one("SELECT 1 FROM users WHERE email='al@x.co'")
    assert dbmod.recent(database)[0]["detail"] == "'; DROP TABLE users; --"


# ------------------------------------------------------------ registration ---
def test_login_page_offers_account_creation(anon):
    page = anon.get("/login")
    assert "Create one" in page.text
    assert "/register" in page.text
    assert "type='email'" in page.text          # email, not a username


def test_register_page_is_reachable_without_a_session(anon):
    page = anon.get("/register")
    assert page.status_code == 200
    assert "CREATE" in page.text and "AN ACCOUNT" in page.text
    assert "Sign in" in page.text               # and a way back
    # Open by default: an email and a password is all it asks for.
    assert "Registration code" not in page.text


def test_registering_signs_you_straight_in(anon):
    """An email and a password is enough; no code is asked for."""
    from cihdt.server import auth

    good = anon.post("/register", data={
        "email": "New@Example.com ", "password": "a-good-password",
        "confirm": "a-good-password", "display_name": "New"},
        follow_redirects=False)
    assert good.status_code == 303
    assert good.headers["location"] == "/"
    assert good.cookies.get("cihdt_session")
    # The address is normalised, so case and spacing cannot make duplicates.
    assert auth.USERS.get("new@example.com") is not None
    assert anon.get("/step/1").status_code == 200


def test_registration_rejects_bad_input(anon):
    from cihdt.server import auth

    def attempt(**over):
        data = {"email": "x@example.com", "password": "a-good-password",
                "confirm": "a-good-password", "display_name": "X"}
        data.update(over)
        return anon.post("/register", data=data)

    assert "not look like an email" in attempt(email="not-an-address").text
    assert "do not match" in attempt(confirm="different-password").text
    assert "at least" in attempt(password="short", confirm="short").text
    # An address already in use must not be silently taken over.
    assert "already exists" in attempt(email=TEST_EMAIL).text
    assert auth.USERS.count == 1


def test_a_code_can_be_required_again(anon, monkeypatch):
    """The stricter policy is one environment variable away."""
    monkeypatch.setenv("CIHDT_REQUIRE_REGISTRATION_CODE", "1")
    from cihdt.server import auth
    assert auth.open_registration() is False

    page = anon.get("/register")
    assert "Registration code" in page.text

    data = {"email": "coded@example.com", "password": "a-good-password",
            "confirm": "a-good-password", "display_name": "Coded"}
    bad = anon.post("/register", data={**data, "code": "nope"})
    assert bad.status_code == 400
    assert "registration code" in bad.text.lower()
    assert auth.USERS.get("coded@example.com") is None

    good = anon.post("/register",
                     data={**data, "code": auth.USERS.registration_code()},
                     follow_redirects=False)
    assert good.status_code == 303
    assert auth.USERS.get("coded@example.com") is not None


def test_registration_is_audited(anon):
    from cihdt.server import db as dbmod
    anon.post("/register", data={
        "email": "audited@example.com", "password": "a-good-password",
        "confirm": "a-good-password", "display_name": "A"})
    actions = {e["action"]: e for e in dbmod.recent(dbmod.DB, limit=20)}
    assert actions["register"]["outcome"] == "ok"
    assert actions["register"]["actor"] == "audited@example.com"


def test_registration_code_survives_a_restart(tmp_path, monkeypatch):
    """A code handed to a colleague must still work after a restart.

    Only meaningful under the stricter policy: with registration open, the
    code check short-circuits and accepts anything.
    """
    monkeypatch.setenv("CIHDT_REQUIRE_REGISTRATION_CODE", "1")
    from cihdt.server import auth, db as dbmod
    path = tmp_path / "code.sqlite3"
    first = auth.UserStore(database=dbmod.Database(path),
                           legacy_path=tmp_path / "absent.json")
    code = first.registration_code()

    reopened = auth.UserStore(database=dbmod.Database(path),
                              legacy_path=tmp_path / "absent.json")
    assert reopened.registration_code() == code
    assert reopened.registration_code_ok(code)
    assert not reopened.registration_code_ok("wrong")


def test_email_is_validated_and_normalised():
    from cihdt.server import auth
    assert auth.valid_email("sai.susanth@vit.ac.in")
    for bad in ("nope", "a@b", "@b.co", "a b@c.co", "a@@b.co", ""):
        assert not auth.valid_email(bad), bad
    assert auth.normalise_email("  Sai@VIT.ac.IN ") == "sai@vit.ac.in"


# ------------------------------------------------- healing preconditions ---
def _warm(tmp_path, monkeypatch, seed=5):
    """A pipeline trained through Step 6, with an isolated registry."""
    import cihdt.pipeline as mod
    monkeypatch.setattr(mod, "MODEL_DIR", tmp_path / "models")
    p = Pipeline(seed=seed)
    p.choose_source("simulated")
    for t in ("smart_camera", "smart_camera", "smart_bulb"):
        p.add_device(t)
    p.start_gateway()
    p.collect(45)
    p.create_twins()
    p.feed_twins()
    p.fit_predictors()
    p.generate_futures()
    p.counterfactual_check()
    p.build_training_corpus(200)
    p.train_detector()
    return p


def test_healing_checks_its_preconditions_before_touching_anything(
        tmp_path, monkeypatch):
    """Healing is irreversible, so it must refuse before it commits.

    It used to roll back, distrust the running model and purge rows, and only
    then discover that the retrain it was about to run needed a validated
    update -- failing with a 409 about a step the operator never asked for,
    with the registry already changed.
    """
    p = _warm(tmp_path, monkeypatch)
    before = p.registry.active_version

    with pytest.raises(StepError) as exc:
        p.self_heal("drill")                 # retrain_after defaults to True
    assert exc.value.required_step == 8

    # Nothing happened at all.
    assert p.registry.active_version == before
    assert p.stats["heals"] == 0
    assert p.registry.get(before).trusted is True


def test_a_healthy_model_is_not_healed_by_accident(tmp_path, monkeypatch):
    """Step 12 recovers a model that went wrong, not one that is working."""
    p = _warm(tmp_path, monkeypatch, seed=6)
    p.launch_attack("smart_camera_01", "ddos", duration=20, intensity=1.0)
    p.monitor(ticks=8)
    for _ in range(3):
        p.health_check()

    check = p.health.last_check
    assert check.evaluated and not check.degraded

    with pytest.raises(StepError, match="healthy"):
        p.self_heal("drill", retrain_after=False)
    assert p.stats["heals"] == 0

    # The override is still available, and says it was used.
    event = p.self_heal("deliberate", retrain_after=False, force=True)["event"]
    assert event["forced"] is True
    assert p.stats["heals"] == 1


def test_healing_a_degraded_model_needs_no_override(tmp_path, monkeypatch):
    """The ordinary path must not have been made harder by the guard."""
    from cihdt.schemas import ThreatVerdict

    p = _warm(tmp_path, monkeypatch, seed=7)
    # Teach the monitor a healthy baseline, then blind the model.
    for _ in range(SETTINGS.heal.baseline_checks):
        for _i in range(30):
            p.health.record(ThreatVerdict(
                device_id="d", predicted_class="ddos", confidence=0.9,
                risk_level="HIGH", twin_flagged=True), twin_ready=True)
        p.health.check()
    for _i in range(60):
        p.health.record(ThreatVerdict(
            device_id="d", predicted_class="normal", confidence=0.9,
            risk_level="NONE", twin_flagged=True), twin_ready=True)
    assert p.health.check().degraded

    event = p.self_heal("compromised", retrain_after=False)["event"]
    assert p.stats["heals"] == 1
    assert event["forced"] is False


# --------------------------------------------------------------- exports ---
def test_a_finished_run_can_be_exported(client):
    """The decision table should reach a report as data, not as retyping."""
    import csv
    import io

    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})

    blob = client.get("/results/export.json")
    assert blob.status_code == 200
    assert "attachment" in blob.headers["content-disposition"]
    payload = blob.json()
    for key in ("exported_by", "steps_complete", "detection", "gate",
                "decisions", "decisions_correct", "decisions_total"):
        assert key in payload, key
    assert payload["exported_by"] == TEST_EMAIL

    sheet = client.get("/results/export.csv")
    assert sheet.status_code == 200
    assert sheet.headers["content-type"].startswith("text/csv")
    header = next(csv.reader(io.StringIO(sheet.text)))
    assert header == ["update_id", "crafted_as", "ccs", "gate", "decision",
                      "attributed_as", "outcome"]


def test_exports_are_audited(client):
    from cihdt.server import db as dbmod
    client.get("/results/export.json")
    client.get("/results/export.csv")
    details = {e["detail"] for e in dbmod.recent(dbmod.DB, limit=20)
               if e["action"] == "export"}
    assert details == {"results.json", "results.csv"}


# ------------------------------------------------- telling you what to do ---
def test_a_locked_step_shows_the_route_to_unlocking_it(client):
    """"Complete Step 5 first" leaves the operator to work out the chain."""
    page = client.get("/step/8")
    assert "This step is locked" in page.text
    # The prerequisite chain, with the one thing that can be done now.
    assert "What has to happen first" in page.text
    assert "do this next" in page.text
    assert "Create the IoT environment" in page.text


def test_a_disabled_control_says_why(client):
    """A greyed button with no reason reads as a broken one."""
    client.post("/step/1/add", data={"device_type": "smart_camera"})
    client.post("/step/1/add", data={"device_type": "smart_bulb"})

    page = client.get("/step/2").text
    assert "disabled" in page
    assert "Start the edge gateway first" in page

    # Step 3 only unlocks once telemetry has actually been collected, and
    # feeding it empties the buffer -- which is when Feed greys out.
    client.post("/step/2/start", data={})
    client.post("/step/2/collect", data={"ticks": 40})
    client.post("/step/3/create", data={})
    client.post("/step/3/feed", data={})
    page = client.get("/step/3").text
    assert "Nothing is buffered" in page
