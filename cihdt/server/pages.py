"""The server-rendered console: one page per step, twelve pages in order.

Every operator action is a POST to ``/step/{n}/{action}`` which runs exactly
one :class:`~cihdt.pipeline.Pipeline` method and then redirects back to
``/step/{n}``.  That Post/Redirect/Get shape is worth the extra round trip: in
a system whose entire premise is that nothing happens unless the operator asks
for it, a page refresh must not re-fire the last action, and with PRG it
cannot.

No JavaScript is served.  Each page is complete HTML built by :mod:`.html`,
which means the browser does no work beyond laying it out, and the page source
is a readable record of what the step actually produced.

Results are kept per ``step/action`` rather than per step, so the output of one
panel never silently wipes another's -- calibrating the gate leaves a
validation report on screen.
"""
from __future__ import annotations

import asyncio
import csv
import io
import time
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import (HTMLResponse, JSONResponse,
                               PlainTextResponse, RedirectResponse)

from ..config import SETTINGS
from ..pipeline import StepError
from ..schemas import ATTACK_CLASSES, DEVICE_TYPES, POISON_STRATEGIES
from ..poisoning.attacks import STRATEGY_TEXT
from . import auth
from . import db
from . import html as H

router = APIRouter()

N_STEPS = 12
VACCINES = [("boundary", "Boundary hardening"),
            ("relabel", "Relabel resistance"),
            ("trigger", "Trigger resistance")]


# ---------------------------------------------------------------------------
# per-session view state
# ---------------------------------------------------------------------------
class ViewState:
    """What the pages remember between requests.

    The pipeline holds the system state; this holds only presentation memory --
    the last result of each panel, the last explanation per step, the values
    the operator typed, and a one-shot error banner.
    """

    def __init__(self) -> None:
        self.last: Dict[str, Dict[str, Any]] = {}
        self.explain: Dict[int, Dict[str, Any]] = {}
        self.form: Dict[int, Dict[str, str]] = {}
        self.flash: Optional[Dict[str, Any]] = None

    def take_flash(self) -> Optional[Dict[str, Any]]:
        message, self.flash = self.flash, None
        return message


VIEW = ViewState()


def reset_view() -> None:
    """Forget every rendered result.  Called when the session is reset."""
    global VIEW
    VIEW = ViewState()


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------
def _ctx():
    """The live pipeline and its lock.

    Imported lazily because :mod:`.api` owns both and rebinds the pipeline on
    reset; resolving it per request is what makes a reset visible here.
    """
    from . import api
    return api.PIPELINE, api.LOCK


def _fv(step: int, key: str, default: Any) -> Any:
    """The value the operator last typed into this field, or a default."""
    return VIEW.form.get(step, {}).get(key, default)


def _int(f: Dict[str, str], key: str, default: int,
         lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(f.get(key, default)))))
    except (TypeError, ValueError):
        return default


def _float(f: Dict[str, str], key: str, default: float,
           lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(f.get(key, default))))
    except (TypeError, ValueError):
        return default


def _str(f: Dict[str, str], key: str, default: str = "") -> str:
    value = f.get(key, default)
    return default if value is None else str(value)


# ---------------------------------------------------------------------------
# action table -- one entry per operator action, mirroring the JSON API
# ---------------------------------------------------------------------------
Handler = Callable[[Any, Dict[str, Any]], Dict[str, Any]]

ACTIONS: Dict[str, Handler] = {
    "0/source": lambda p, f: p.choose_source(_str(f, "mode", "simulated")),
    "0/scan": lambda p, f: p.scan_usb(),

    "1/add": lambda p, f: p.add_device(_str(f, "device_type")),
    "1/scan": lambda p, f: p.scan_usb(),
    "1/enrol": lambda p, f: p.add_live_device(
        _str(f, "slug"), _str(f, "device_type") or None),
    "1/remove": lambda p, f: p.remove_device(_str(f, "device_id")),
    "1/select": lambda p, f: p.select_device(_str(f, "device_id")),

    "2/start": lambda p, f: p.start_gateway(),
    "2/collect": lambda p, f: p.collect(_int(f, "ticks", 45, 1, 400)),

    "3/create": lambda p, f: p.create_twins(),
    "3/feed": lambda p, f: p.feed_twins(),

    "4/fit": lambda p, f: p.fit_predictors(),

    "5/futures": lambda p, f: p.generate_futures(
        _int(f, "n_futures", SETTINGS.twin.n_futures, 3, 80),
        _int(f, "horizon", SETTINGS.twin.horizon, 1, 20)),
    "5/check": lambda p, f: p.counterfactual_check(),

    "6/corpus": lambda p, f: p.build_training_corpus(
        _int(f, "rows_per_class", 380, 80, 1200)),
    "6/train": lambda p, f: p.train_detector(),
    "6/attack": lambda p, f: p.launch_attack(
        _str(f, "device_id"), _str(f, "attack", "ddos"),
        _int(f, "duration", 15, 1, 400),
        _float(f, "intensity", 1.0, 0.05, 1.0)),
    "6/stop": lambda p, f: p.stop_attack(_str(f, "device_id")),
    "6/monitor": lambda p, f: p.monitor(_int(f, "ticks", 5, 1, 60)),

    "7/craft": lambda p, f: p.craft_update(
        _str(f, "strategy", "label_flip"), None,
        _int(f, "rows", 240, 40, 1500),
        _float(f, "potency", 1.0, 0.05, 1.0)),
    "7/discard": lambda p, f: p.discard_update(_str(f, "update_id")),

    "8/bank": lambda p, f: p.refresh_bank(),
    "8/calibrate": lambda p, f: p.calibrate_gate(
        _int(f, "honest_updates", 8, 3, 20)),
    "8/validate": lambda p, f: p.validate_update(_str(f, "update_id")),
    "8/apply": lambda p, f: p.apply_decision(
        _str(f, "update_id"), _str(f, "override") or None),

    "9/vaccine": lambda p, f: p.generate_vaccine(
        f.get("vaccines") or None,
        _int(f, "scenarios", SETTINGS.immune.scenarios_per_strategy, 7, 200)),
    "9/resistance": lambda p, f: p.measure_resistance(),

    "10/analyse": lambda p, f: p.analyse_quarantined(_str(f, "update_id")),
    "10/release": lambda p, f: p.release_quarantined(_str(f, "update_id")),
    "10/rescore": lambda p, f: p.rescore_quarantine(False),

    "11/retrain": lambda p, f: p.retrain(_str(f, "immunize", "yes") == "yes"),

    "12/check": lambda p, f: p.health_check(),
    "12/heal": lambda p, f: p.self_heal(
        _str(f, "reason", "operator-triggered") or "operator-triggered",
        _str(f, "retrain_after", "") == "yes",
        force=_str(f, "force", "") == "yes"),
    "12/rollback": lambda p, f: p.rollback_to(_int(f, "version", 1, 1, 9999)),
}

# Fields that are remembered for the next render of the same step.
STICKY = {"ticks", "n_futures", "horizon", "rows_per_class", "duration",
          "mode",
          "intensity", "attack", "device_id", "strategy", "rows", "potency",
          "honest_updates", "scenarios", "immunize", "reason",
          "retrain_after", "force", "vaccines"}


# Where each action's own panel sits on its page.
#
# Every action is a full page load, so without this the browser would drop the
# operator back at the top after every click -- which is exactly what it used
# to do.  The POST redirects to the card whose button was pressed, and the page
# comes back where it was left, with that panel's fresh result in view.
ANCHORS: Dict[str, str] = {
    "1/add": "device-catalogue",
    "1/remove": "deployed-network",
    "1/select": "deployed-network",
    "1/scan": "attached-usb-devices",
    "1/enrol": "monitored-devices",

    "2/start": "edge-gateway",
    "2/collect": "collect-telemetry",

    "3/create": "create-and-feed-twins",
    "3/feed": "create-and-feed-twins",

    "4/fit": "fit-the-forward-models",

    "5/futures": "commit-to-counterfactual-futures",
    "5/check": "score-reality-against-the-commitment",

    "6/corpus": "training-corpus",
    "6/train": "edge-threat-detector",
    "6/attack": "launch-an-attack-by-hand",
    "6/stop": "launch-an-attack-by-hand",
    "6/monitor": "live-protection-loop",

    "7/craft": "inbox",
    "7/discard": "inbox",

    "8/bank": "the-audit-bank-and-the-gate",
    "8/calibrate": "the-audit-bank-and-the-gate",
    "8/validate": "validation-report",
    "8/apply": "updates-awaiting-a-decision",

    "9/vaccine": "manufacture-vaccines-from-predicted-futures",
    "9/resistance": "measure-poison-resistance",

    "10/analyse": "forensic-analysis",
    "10/release": "quarantine-zone",
    "10/rescore": "quarantine-zone",

    "11/retrain": "retraining-outcome",

    "12/check": "model-health",
    "12/heal": "heal-roll-back-purge-rebuild",
    "12/rollback": "roll-back-by-hand",
}

# The same idea for the pages that are not one of the twelve.
PAGE_ANCHORS: Dict[str, str] = {
    "/accounts/add": "add-an-account",
    "/accounts/password": "change-a-password",
    "/accounts/remove": "who-can-sign-in",
}


def _back_to(path: str) -> str:
    """The path with the fragment that lands on the panel that was used."""
    fragment = PAGE_ANCHORS.get(path)
    return f"{path.rsplit('/', 1)[0]}#{fragment}" if fragment else path

async def _read_form(request: Request) -> Dict[str, Any]:
    """Parse an urlencoded form, keeping repeated keys as a list."""
    raw = await request.form()
    out: Dict[str, Any] = {}
    for key in raw.keys():
        values = raw.getlist(key)
        out[key] = values if len(values) > 1 else values[0]
    if "vaccines" in raw:
        out["vaccines"] = raw.getlist("vaccines")
    return out


def _step_target(step: int, key: str) -> str:
    """``/step/N`` with the fragment for the panel this action belongs to."""
    fragment = ANCHORS.get(key)
    return f"/step/{step}#{fragment}" if fragment else f"/step/{step}"


@router.post("/step/{step}/{action}")
async def run_action(step: int, action: str, request: Request):
    key = f"{step}/{action}"
    handler = ACTIONS.get(key)
    if handler is None:
        raise HTTPException(404, f"no action {key!r}")

    pipeline, lock = _ctx()
    form = await _read_form(request)
    remembered = {k: v for k, v in form.items()
                  if k in STICKY and isinstance(v, str)}
    if "vaccines" in form:
        remembered["vaccines"] = ",".join(form["vaccines"])
    VIEW.form.setdefault(step, {}).update(remembered)

    async with lock:
        try:
            result = await asyncio.to_thread(handler, pipeline, form)
        except StepError as exc:
            _audit(request, f"step{key}", str(exc)[:200], "refused")
            VIEW.flash = {"message": str(exc),
                          "required_step": exc.required_step}
            # Land on the control that was refused, not at the top of the
            # page. The flash banner is sticky, so the reason stays in view
            # from wherever the operator is standing.
            return RedirectResponse(_step_target(step, key), status_code=303)
        except Exception as exc:                             # pragma: no cover
            VIEW.flash = {"message": f"{type(exc).__name__}: {exc}",
                          "required_step": None}
            return RedirectResponse(_step_target(step, key), status_code=303)

    _audit(request, f"step{key}", result.get("summary", ""))
    VIEW.last[key] = result
    if result.get("explanation"):
        VIEW.explain[step] = result["explanation"]

    if step == 0:
        if action == "source" and pipeline.source_mode:
            return RedirectResponse("/step/1", status_code=303)
        return RedirectResponse("/start#live-usb-devices", status_code=303)

    target = f"/step/{step}"
    if action == "validate":
        target += f"?report={result.get('report', {}).get('update_id', '')}"
    elif action == "analyse":
        target += f"?record={_str(form, 'update_id')}"

    # Land on the panel the operator pressed, not at the top of the page.
    fragment = ANCHORS.get(key)
    if fragment:
        target += f"#{fragment}"
    return RedirectResponse(target, status_code=303)


# ---------------------------------------------------------------------------
# signing in and out
# ---------------------------------------------------------------------------
def _who(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return (user or {}).get("email", "")


def _client_ip(request: Request) -> str:
    return getattr(request.client, "host", "") or ""


def _audit(request: Request, action: str, detail: str = "",
           outcome: str = "ok") -> None:
    """Record one operator action against the signed-in account."""
    db.record(db.DB, _who(request), action, detail, outcome,
              _client_ip(request))


def _safe_next(target: str) -> str:
    """Only ever redirect somewhere on this site.

    `next` arrives from the query string, so an open redirect here would let a
    crafted sign-in link bounce an operator to an attacker's page carrying the
    appearance of having come from the console.
    """
    target = (target or "/").strip()
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return target


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if auth.SESSIONS.resolve(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(H.auth_page(
        next_url=_safe_next(request.query_params.get("next", "/")),
        notice=("No accounts existed, so one was created. Its password was "
                "printed in the terminal that started the server."
                if auth.USERS.initial_password else "")))


@router.post("/login")
async def login_submit(request: Request):
    form = await _read_form(request)
    email = _str(form, "email")
    nxt = _safe_next(_str(form, "next", "/"))

    wait = auth.USERS.locked_for(email)
    if wait > 0:
        return HTMLResponse(H.auth_page(
            error=f"Too many attempts. Try again in {int(wait) + 1} seconds.",
            next_url=nxt, email=email), status_code=429)

    user = await asyncio.to_thread(auth.USERS.authenticate, email,
                                   _str(form, "password"))
    if user is None:
        db.record(db.DB, auth.normalise_email(email), "login", "", "refused",
                  _client_ip(request))
        # One message for both causes: a different answer for "no such
        # account" would enumerate addresses.
        return HTMLResponse(H.auth_page(
            error="Those credentials were not recognised.",
            next_url=nxt, email=email), status_code=401)

    token = auth.SESSIONS.create(
        user.email, ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""))
    db.record(db.DB, user.email, "login", "", "ok", _client_ip(request))
    response = RedirectResponse(nxt, status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME, token, httponly=True, samesite="lax", path="/",
        max_age=auth.SESSION_IDLE_SECONDS)
    return response


# ---------------------------------------------------------------------------
# creating an account
# ---------------------------------------------------------------------------
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if auth.SESSIONS.resolve(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(H.register_page(
        needs_code=not auth.open_registration()))


@router.post("/register")
async def register_submit(request: Request):
    form = await _read_form(request)
    email = _str(form, "email")
    display_name = _str(form, "display_name")

    try:
        user = await asyncio.to_thread(
            auth.USERS.register, email, _str(form, "password"),
            _str(form, "confirm"), display_name, _str(form, "code"))
    except ValueError as exc:
        db.record(db.DB, auth.normalise_email(email), "register",
                  str(exc)[:200], "refused", _client_ip(request))
        return HTMLResponse(H.register_page(
            error=str(exc), email=email, display_name=display_name,
            needs_code=not auth.open_registration()), status_code=400)

    db.record(db.DB, user.email, "register", "account created", "ok",
              _client_ip(request))
    # Sign the new operator straight in; making them retype what they just
    # typed serves nobody.
    token = auth.SESSIONS.create(
        user.email, ip=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""))
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.COOKIE_NAME, token, httponly=True, samesite="lax", path="/",
        max_age=auth.SESSION_IDLE_SECONDS)
    return response


@router.post("/logout")
async def logout(request: Request):
    _audit(request, "logout")
    auth.SESSIONS.destroy(request.cookies.get(auth.COOKIE_NAME))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return response


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------
@router.get("/accounts", response_class=HTMLResponse)
async def accounts_page(request: Request):
    return HTMLResponse(H.plain_page(
        title_text="Console accounts",
        eyebrow="Access — who may operate this console",
        lede="Everyone who uses the console signs in. Passwords are stored "
             "only as a salted PBKDF2 derivation, never in the clear.",
        body=_accounts_body(), message=VIEW.take_flash(),
        user=getattr(request.state, "user", None)))


def _accounts_body() -> str:
    rows = []
    for u in auth.USERS.list_users():
        last = (time.strftime("%Y-%m-%d %H:%M",
                              time.localtime(u["last_login"]))
                if u["last_login"] else "never")
        rows.append([
            f"<code>{H.esc(u['email'])}</code>",
            H.esc(u["display_name"]),
            H.esc(last),
            H.form("/accounts/remove", "Remove",
                   fields={"email": u["email"]}, kind="ghost sm",
                   inline=True) if auth.USERS.count > 1 else
            H.badge("only account", "pending"),
        ])

    listing = H.card(
        "Who can sign in",
        H.table(["Email", "Name", "Last signed in", ""], rows),
        hint=f"{H.plural(auth.USERS.count, 'account')}, "
             f"{auth.SESSIONS.active} active session(s).")

    add = H.card(
        "Add an account",
        H.form("/accounts/add", "Create account",
               body=H.controls(
                   H.field("email", "Email address", "", kind="email"),
                   H.field("display_name", "Display name", "", kind="text"),
                   H.field("password", "Password", "", kind="password"))),
        hint="Passwords must be at least eight characters and are hashed "
             "before they touch disk.")

    change = H.card(
        "Change a password",
        H.form("/accounts/password", "Set password",
               body=H.controls(
                   H.field("email", "Email address", "", kind="email"),
                   H.field("password", "New password", "", kind="password"))),
        hint="Changing a password does not sign that operator out of sessions "
             "they already hold; remove and re-add the account to do that.")

    if auth.open_registration():
        invite = H.card(
            "Self-registration",
            H.note("Anyone who can reach this console may create their own "
                   "account at /register with an email and a password. No "
                   "code is required."),
            aside=H.badge("open", "accent"),
            hint="Appropriate while the console is reachable only by people "
                 "who should operate it. If that stops being true, set "
                 "CIHDT_REQUIRE_REGISTRATION_CODE=1 and enrolment will ask "
                 "for a shared code instead.")
    else:
        invite = H.card(
            "Self-registration",
            H.kv_list([("Registration code", auth.USERS.registration_code())]),
            aside=H.badge("code required", "ok"),
            hint="Anyone with this code can enrol themselves at /register. "
                 "Give it only to people who should be able to operate the "
                 "console; it is as good as an account.")

    return listing + invite + add + change


@router.post("/accounts/add")
async def accounts_add(request: Request):
    form = await _read_form(request)
    try:
        await asyncio.to_thread(
            auth.USERS.add_user, _str(form, "email"),
            _str(form, "password"), _str(form, "display_name"))
    except ValueError as exc:
        _audit(request, "account.add", str(exc)[:200], "refused")
        VIEW.flash = {"message": str(exc), "required_step": None}
        return RedirectResponse(_back_to("/accounts/add"), status_code=303)
    _audit(request, "account.add", _str(form, "email"))
    return RedirectResponse(_back_to("/accounts/add"), status_code=303)


@router.post("/accounts/password")
async def accounts_password(request: Request):
    form = await _read_form(request)
    try:
        await asyncio.to_thread(auth.USERS.set_password,
                                _str(form, "email"), _str(form, "password"))
    except ValueError as exc:
        _audit(request, "account.password", str(exc)[:200], "refused")
        VIEW.flash = {"message": str(exc), "required_step": None}
        return RedirectResponse(_back_to("/accounts/password"),
                                status_code=303)
    _audit(request, "account.password", _str(form, "email"))
    return RedirectResponse(_back_to("/accounts/password"), status_code=303)


@router.post("/accounts/remove")
async def accounts_remove(request: Request):
    form = await _read_form(request)
    email = _str(form, "email")
    try:
        await asyncio.to_thread(auth.USERS.remove_user, email)
        # An account that no longer exists must not keep an open console.
        auth.SESSIONS.destroy_for_user(email)
    except ValueError as exc:
        _audit(request, "account.remove", str(exc)[:200], "refused")
        VIEW.flash = {"message": str(exc), "required_step": None}
        return RedirectResponse(_back_to("/accounts/remove"), status_code=303)
    _audit(request, "account.remove", _str(form, "email"))
    return RedirectResponse(_back_to("/accounts/remove"), status_code=303)


@router.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    """The audit trail, and what the database itself looks like."""
    limit = _int({"n": request.query_params.get("n", 120)}, "n", 120, 20, 500)
    entries = await asyncio.to_thread(db.recent, db.DB, limit)
    stats = await asyncio.to_thread(db.DB.stats)
    sessions = await asyncio.to_thread(auth.SESSIONS.list_sessions)
    return HTMLResponse(H.plain_page(
        title_text="Console activity",
        eyebrow="Audit — who did what, and when",
        lede="Every operator action is recorded against the account that ran "
             "it. A security console that cannot say who rolled the model "
             "back is missing the first record an incident review asks for.",
        body=_activity_body(entries, sessions, stats),
        message=VIEW.take_flash(),
        user=getattr(request.state, "user", None)))


def _activity_body(entries: List[Dict[str, Any]],
                   sessions: List[Dict[str, Any]],
                   stats: Dict[str, Any]) -> str:
    tone = {"ok": "ok", "refused": "warn"}
    rows = []
    for e in entries:
        rows.append([
            H.esc(time.strftime("%Y-%m-%d %H:%M:%S",
                                time.localtime(e["at"]))),
            H.esc(e["actor"] or "—"),
            f"<code>{H.esc(e['action'])}</code>",
            H.badge(e["outcome"], tone.get(e["outcome"], "")),
            f"<small>{H.esc(e['detail'])}</small>",
        ])
    trail = H.card(
        "Audit trail",
        H.table(["When", "Account", "Action", "Outcome", "Detail"], rows)
        or H.empty("Nothing recorded yet."),
        hint=f"The {len(entries)} most recent entries, newest first. Refused "
             f"actions are kept too -- an attempt that was blocked is as "
             f"interesting as one that succeeded.")

    srows = [[f"<code>{H.esc(x['token'])}</code>", H.esc(x["email"]),
              H.esc(time.strftime("%H:%M:%S", time.localtime(x["last_seen"]))),
              H.esc(x["ip"] or "—"),
              f"<small>{H.esc((x['user_agent'] or '')[:60])}</small>"]
             for x in sessions]
    live = H.card(
        "Open sessions",
        H.table(["Token", "Account", "Last seen", "From", "Client"], srows)
        or H.empty("No open sessions."),
        hint="Tokens are shown truncated on purpose: a full one on screen is "
             "a session somebody could take.")

    store = H.card(
        "Storage",
        H.metrics([
            ("Engine", stats["engine"]),
            ("Schema", f"v{stats['schema_version']}"),
            ("Users", stats["users"]),
            ("Sessions", stats["sessions"]),
            ("Audit rows", stats["audit_entries"]),
            ("Size", f"{stats['size_kb']} kB"),
            ("Journal", stats["journal_mode"]),
        ]) + H.kv_list([("Database file", stats["path"])]),
        hint="SQLite, through the standard library. A client/server database "
             "would add a process to install and a port to listen on, to a "
             "console whose premise is that nothing leaves the local network.")

    return trail + live + store


# ---------------------------------------------------------------------------
# what the run proved
# ---------------------------------------------------------------------------
@router.get("/results", response_class=HTMLResponse)
async def results_page(request: Request):
    """The conclusion: the twelve steps read back as one verdict.

    Reaching Step 12 leaves the evidence scattered over six pages. This
    gathers it, states what it supports, and says plainly what it does not --
    because the limitation an examiner finds for themselves costs more than
    the one that was declared.
    """
    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
    done = sum(1 for sp in state["steps"] if sp["status"] == "done")
    return HTMLResponse(H.plain_page(
        title_text="What this run proved",
        eyebrow=f"Conclusion \u2014 {done} of 12 steps complete",
        lede="Every figure below was produced by this console during this "
             "session. Nothing here is quoted from a previous run.",
        body=_results_body(state, done), message=VIEW.take_flash(),
        user=getattr(request.state, "user", None)))


def _results_body(state: Dict[str, Any], done: int) -> str:
    if done < 12:
        remaining = [sp for sp in state["steps"] if sp["status"] != "done"]
        rows = [[H.esc(f"{sp['id']:02d}"), H.esc(sp["title"]),
                 H.badge(sp["status"], "pending" if sp["status"] == "locked"
                         else "accent")]
                for sp in remaining]
        return H.card(
            "The run is not finished",
            H.metrics([("Complete", f"{done} of 12"),
                       ("Outstanding", len(remaining))])
            + H.table(["#", "Step", "State"], rows)
            + f"<p><a class='btn' href='/step/{remaining[0]['id']}'>"
              f"Continue at Step {remaining[0]['id']} &rarr;</a></p>",
            anchor="not-finished",
            hint="A conclusion drawn from a partial run would be worth less "
                 "than no conclusion. Finish the twelve steps and come back.")

    return (_verdict_band(state) + _detection_card(state)
            + _gate_card(state) + _defence_card(state)
            + _export_card() + _limits_card(state))


def _export_card() -> str:
    return H.card(
        "Take this run with you",
        H.row("<a class='btn' href='/results/export.json'>"
              "Download JSON</a>",
              "<a class='btn ghost' href='/results/export.csv'>"
              "Download decision table (CSV)</a>"),
        anchor="export",
        hint="Every figure on this page, as data. The CSV is the decision "
             "table above, ready to paste into a report rather than retyped "
             "off a screen -- which is how a transcription error ends up in "
             "a dissertation.")


def _scoreboard(state: Dict[str, Any]) -> Dict[str, Any]:
    """Was each decision right, measured against the simulator's own record?

    One row per contribution, not one per scoring.  Rescoring the quarantine
    in Step 10 puts every held update through the gate a second time, and
    counting those again would inflate the result with decisions the framework
    was never asked to make twice.  The first verdict is the one under test;
    the rescores are reported separately because what they say -- whether a
    better bank would change its mind -- is a different question.
    """
    rows, correct, seen, rescored = [], 0, set(), 0
    for v in state.get("validations") or []:
        if v.get("update_id") in seen:
            rescored += 1
            continue
        seen.add(v.get("update_id"))
        declared = v.get("declared", "clean")
        accepted = v["decision"] == "ACCEPTED"
        right = accepted if declared == "clean" else not accepted
        correct += int(right)
        rows.append({**v, "correct": right})
    return {"rows": rows, "correct": correct, "total": len(rows),
            "rescored": rescored}


def _verdict_band(state: Dict[str, Any]) -> str:
    board = _scoreboard(state)
    model = state.get("model") or {}
    threshold = (state.get("validator") or {}).get("threshold")

    if not board["total"]:
        headline = ("<h2><b>NO UPDATE</b><span>WAS VALIDATED</span></h2>"
                    "<p>The twelve steps ran, but nothing was put through the "
                    "gate, so there is no verdict to report.</p>")
        cls = "band continue pending"
    else:
        perfect = board["correct"] == board["total"]
        cls = "band continue" if perfect else "band continue pending"
        headline = (
            f"<p class='eyebrow'>The decision the framework exists to make</p>"
            f"<h2><b>{board['correct']} OF {board['total']}</b>"
            f"<span>DECISIONS CORRECT</span></h2>"
            f"<p>Every contribution was scored against futures the twins "
            f"committed to before it existed, at a gate of "
            f"{H.num(threshold, 3)} calibrated from this fleet rather than "
            f"chosen by hand.</p>")

    chips = H.metrics([
        ("Accuracy", H.pct(model.get("accuracy")), "edge detector"),
        ("False negatives", H.pct(model.get("false_negative_rate")),
         "attacks called benign"),
        ("Accept gate", H.num(threshold, 4), "calibrated"),
        ("Accepted", state["stats"]["accepted"], "into the safe pool"),
        ("Quarantined", state["stats"]["quarantined"], "held back"),
        ("Model version", f"v{model.get('version', '?')}", "in service"),
    ])
    return (f"<section class='{cls}'><div class='wrap narrow'>{headline}"
            f"</div></section>"
            f"<section class='card' id='headline'>"
            f"<header><h2>Headline figures</h2></header>{chips}</section>")


def _detection_card(state: Dict[str, Any]) -> str:
    model = state.get("model") or {}
    corpus = state.get("corpus") or {}
    body = H.kv_list([
        ("Telemetry source", (state.get("source_mode") or "simulated")),
        ("Devices monitored", state["fleet"]["n_devices"]),
        ("Observations collected", state["stats"]["observations"]),
        ("Corpus rows", corpus.get("rows", "--")),
        ("Benign class drawn from", corpus.get("normal_from", "--")),
        ("Accuracy", H.pct(model.get("accuracy"))),
        ("Macro F1", H.pct(model.get("macro_f1"))),
        ("False positive rate", H.pct(model.get("false_positive_rate"))),
        ("False negative rate", H.pct(model.get("false_negative_rate"))),
        ("Twin flags raised", state["stats"]["twin_flags"]),
        ("Model detections", state["stats"]["detections"]),
    ])
    return H.card(
        "What the detector and the twins achieved", body, anchor="detection",
        hint="The twin and the classifier are independent readings of the "
             "same events. Their agreement is what the self-healing monitor "
             "watches, which is why both counts are reported.")


def _gate_card(state: Dict[str, Any]) -> str:
    """The core result: every update, its score, and whether the call was right."""
    board = _scoreboard(state)
    if not board["total"]:
        return H.card("Counterfactual validation",
                      H.empty("No update was validated during this run."),
                      anchor="the-gate")

    rows = []
    for v in board["rows"]:
        rows.append([
            H.esc(H.human(v.get("declared", "clean"))),
            H.num(v["ccs"], 3),
            H.badge(v["decision"].title(),
                    "ok" if v["decision"] == "ACCEPTED" else "attack"),
            H.esc(H.human(v.get("suspected", ""))),
            H.badge("correct", "ok") if v["correct"]
            else H.badge("wrong", "bad"),
        ])

    cal = (state.get("validator") or {}).get("calibration") or {}
    pairs = [("Honest mean CCS", H.num(cal.get("honest_mean"), 4)),
             ("Honest spread", H.num(cal.get("honest_std"), 4)),
             ("Calibrated gate", H.num(cal.get("threshold"), 4)),
             ("Bank scenarios", state["bank"]["n"])]
    if board["rescored"]:
        pairs.append(("Rescored in Step 10", board["rescored"]))
    detail = H.kv_list(pairs) if cal.get("calibrated") else ""

    note = H.note(
        "Clean-label poisoning is the row that matters. Its label mix barely "
        "moves, so every distributional defence accepts it; only the "
        "cross-check against the trusted model's reading of its own rows "
        "sees it.")

    return H.card(
        "Counterfactual validation \u2014 the core result",
        detail + H.table(
            ["Crafted as", ("CCS", "num"), "Decision", "Attributed as",
             "Outcome"], rows) + note,
        anchor="the-gate",
        aside=H.badge(f"{board['correct']}/{board['total']}",
                      "ok" if board["correct"] == board["total"] else "warn"),
        hint="Each update was grafted onto a trusted core, a shadow model "
             "trained, and that shadow put in front of futures committed "
             "before the update existed.")


def _defence_card(state: Dict[str, Any]) -> str:
    res = state.get("resistance") or {}
    registry = state.get("registry") or {}
    health = state.get("last_check") or {}

    body = ""
    if res.get("per_strategy"):
        body += H.metrics([
            ("Poison resistance", H.num(res["poison_resistance"], 4), "",
             H.tone_for(res["poison_resistance"], 0.85, 0.7)),
            ("Weakest against", H.human(res.get("weakest"))),
            ("Scenarios tested", res.get("scenarios_tested", "--")),
        ])
        body += H.table(
            ["Rehearsed strategy", ("Surviving attack recall", "num"), ""],
            [[H.esc(H.human(k)), H.num(v, 4),
              H.bar(v, H.tone_for(v, 0.9, 0.78))]
             for k, v in res["per_strategy"].items()])

    body += H.kv_list([
        ("Retrains run", state["stats"]["retrains"]),
        ("Models promoted", state["stats"]["promotions"]),
        ("Versions in the registry", registry.get("count", 0)),
        ("Safe pool rows", state["retrainer"]["pool_size"]),
        ("Vaccine generations", state["immunizer"]["generations"]),
        ("Heals performed", state["stats"]["heals"]),
        ("Model/twin agreement",
         H.num(health.get("agreement"), 3) if health.get("evaluated")
         else "not evaluated"),
    ])
    return H.card(
        "Immunization, retraining and recovery", body, anchor="defence",
        hint="A backdoored model scores beautifully on accuracy -- that is "
             "the point of a backdoor -- so the poison-resistance gate is the "
             "one that earns its place in the promotion decision.")


def _limits_card(state: Dict[str, Any]) -> str:
    live = bool(state.get("is_live"))
    limits = [
        "Strategy attribution is rule-based, not learned. A learned "
        "attributor would need labelled poison to train on, and if we had "
        "that we would not need the defence.",
        "Poison resistance is measured against the five rehearsed "
        "strategies. An attacker using a sixth is outside that number.",
        "label_agreement trusts the incumbent model, so an update carrying a "
        "genuinely novel attack pattern would be penalised by that term. It "
        "is one of six for exactly this reason.",
    ]
    if live:
        limits.insert(0,
            "The devices are real, but a USB peripheral has no network stack: "
            "ten of the sixteen features are measured from the host and "
            "attributed to the device, and two cannot be obtained at all. "
            "Attack rows are synthesised on top of measured normal.")
        limits.insert(1,
            "Live devices all sample one host, so their baselines are nearly "
            "identical. That is an easier problem than a heterogeneous fleet, "
            "and any accuracy above the simulated figure reflects the "
            "difference in difficulty, not a better model.")
    else:
        limits.insert(0,
            "The fleet is simulated from behavioural profiles, not captured "
            "from real hardware. The profiles are physically motivated but "
            "they are not a packet capture.")

    return H.card(
        "What this run does not establish", H.findings(limits),
        anchor="limits",
        hint="Stated here because these are the questions a good examiner "
             "asks, and a limitation they find for themselves costs more "
             "than one that was declared.")



@router.get("/results/export.json")
async def export_json(request: Request):
    """The whole run as one JSON document."""
    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
    board = _scoreboard(state)
    model = state.get("model") or {}
    cal = (state.get("validator") or {}).get("calibration") or {}
    payload = {
        "exported_at": time.time(),
        "exported_by": _who(request),
        "source_mode": state.get("source_mode"),
        "steps_complete": sum(1 for sp in state["steps"]
                              if sp["status"] == "done"),
        "fleet": state["fleet"],
        "corpus": state.get("corpus"),
        "detection": {k: model.get(k) for k in
                      ("version", "accuracy", "macro_f1",
                       "false_positive_rate", "false_negative_rate")},
        "gate": {"threshold": (state.get("validator") or {}).get("threshold"),
                 "honest_mean": cal.get("honest_mean"),
                 "honest_std": cal.get("honest_std"),
                 "bank_scenarios": state["bank"]["n"]},
        "decisions": board["rows"],
        "decisions_correct": board["correct"],
        "decisions_total": board["total"],
        "rescored": board["rescored"],
        "resistance": state.get("resistance"),
        "registry": state["registry"]["lineage"],
        "stats": state["stats"],
    }
    _audit(request, "export", "results.json")
    return JSONResponse(payload, headers={
        "Content-Disposition": 'attachment; filename="cihdt-run.json"'})


@router.get("/results/export.csv")
async def export_csv(request: Request):
    """The decision table as CSV, for pasting into a report."""
    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
    board = _scoreboard(state)
    threshold = (state.get("validator") or {}).get("threshold")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["update_id", "crafted_as", "ccs", "gate", "decision",
                     "attributed_as", "outcome"])
    for row in board["rows"]:
        writer.writerow([
            row.get("update_id", ""), row.get("declared", "clean"),
            f"{row['ccs']:.4f}", f"{threshold:.4f}" if threshold else "",
            row["decision"], row.get("suspected", ""),
            "correct" if row["correct"] else "wrong"])
    _audit(request, "export", "results.csv")
    return PlainTextResponse(buffer.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition":
                                      'attachment; filename="cihdt-run.csv"'})


# ---------------------------------------------------------------------------
# step pages
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """The front door: what the framework is, and the twelve steps."""
    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
    return HTMLResponse(H.landing(state, VIEW.take_flash(),
                                  user=getattr(request.state, "user", None)))


@router.get("/start", response_class=HTMLResponse)
async def start_page(request: Request):
    """Where does the telemetry come from? The question before Step 1."""
    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
    return HTMLResponse(H.plain_page(
        title_text="Choose your telemetry source",
        eyebrow="Step 00 of 12 — before anything is deployed",
        lede="Everything after this is identical. The twelve steps do not know "
             "whether the numbers they are reading came from a behavioural "
             "model or from the USB bus of this laptop.",
        body=_source_body(state), message=VIEW.take_flash(),
        user=getattr(request.state, "user", None)))


def _source_body(state: Dict[str, Any]) -> str:
    support = state.get("live_support") or {}
    live_ok = bool(support.get("available"))
    mode = state.get("source_mode")
    deployed = state["fleet"]["n_devices"] > 0

    sim = H.card(
        "Simulated fleet",
        H.form("/step/0/source", "Use the simulated fleet",
               fields={"mode": "simulated"}, disabled=deployed)
        + (H.badge("in use", "accent") if mode == "simulated" else ""),
        hint="Six consumer device types built from behavioural profiles, each "
             "with its own drift and activity cycle. Every one of the sixteen "
             "features is produced, every attack class can genuinely be "
             "launched, and the run is reproducible from a seed.")

    if live_ok:
        counts = support.get("provenance_counts", {})
        live_body = (
            H.form("/step/0/source", "Use live USB devices",
                   fields={"mode": "live"}, disabled=deployed)
            + (H.badge("in use", "accent") if mode == "live" else "")
            + H.metrics([
                ("Measured from host", counts.get("host", 0), "of 16 features"),
                ("Measured from device", counts.get("device", 0),
                 "presence, stability"),
                ("Declared", counts.get("declared", 0), "USB bus power"),
                ("Unavailable", counts.get("unavailable", 0),
                 "reported, never invented",
                 "warn" if counts.get("unavailable") else ""),
            ]))
    else:
        live_body = (H.note(support.get("reason")
                            or "Live sampling is not available on this host.")
                     + H.form("/step/0/source", "Use live USB devices",
                              fields={"mode": "live"}, disabled=True))

    live = H.card(
        "Live USB devices",
        live_body,
        hint="Real peripherals attached to this machine — a webcam, a "
             "headset, a Bluetooth radio — enrolled by name and sampled "
             "through the host they are plugged into.",
        aside=H.badge("available" if live_ok else "unavailable",
                      "ok" if live_ok else "pending"))

    disclosure = ""
    if live_ok and support.get("rows"):
        rows = []
        tone = {"host": "accent", "device": "ok", "declared": "warn",
                "unavailable": "bad"}
        for r in support["rows"]:
            rows.append([
                f"<code>{H.esc(r['feature'])}</code>",
                H.badge(r["provenance"], tone.get(r["provenance"], "")),
                f"<small>{H.esc(r['how'])}</small>",
            ])
        disclosure = H.card(
            "What live mode can and cannot measure",
            H.table(["Feature", "Provenance", "How it is obtained"], rows),
            hint="A USB webcam has no network stack. It has no address, opens "
                 "no sockets and authenticates nobody, so the network planes "
                 "cannot be measured from the device and are measured from its "
                 "host instead — which is exactly where a compromised "
                 "peripheral's traffic would appear. Two features cannot be "
                 "obtained here at all; they are reported as missing rather "
                 "than invented.")

    nxt = ""
    if mode:
        nxt = ("<section class='band continue'><div class='wrap narrow'>"
               f"<p class='eyebrow'>Source chosen: {H.esc(mode)}</p>"
               "<h2><b>CREATE</b><span>THE IOT ENVIRONMENT</span></h2>"
               "<p>Pick the devices this console will monitor.</p>"
               "<a class='btn big' href='/step/1'>Continue to Step 1 &rarr;"
               "</a></div></section>")
    if deployed:
        nxt = H.note("Devices are already deployed from the "
                     f"{mode} source. Reset the console to change it.") + nxt

    return sim + live + disclosure + nxt


@router.get("/step/{step}", response_class=HTMLResponse)
async def step_page(step: int, request: Request):
    if step < 1 or step > N_STEPS:
        raise HTTPException(404, "no such step")

    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
        extra = await asyncio.to_thread(_page_extras, pipeline, step,
                                        dict(request.query_params))

    spec = next(s for s in state["steps"] if s["id"] == step)
    if spec["status"] == "locked":
        body = _locked_body(state, spec)
    else:
        body = (H.explanation(VIEW.explain.get(step))
                + RENDERERS[step](state, extra))

    return HTMLResponse(H.page(
        title_text=spec["title"], state=state, current=step, body=body,
        eyebrow=f"Step {step:02d} of {N_STEPS} — {spec['subtitle']}",
        lede=spec["purpose"], message=VIEW.take_flash(),
        user=getattr(request.state, "user", None)))



def _locked_body(state: Dict[str, Any], spec: Dict[str, Any]) -> str:
    """A locked step, with the route to unlocking it.

    Saying only "complete Step 5 first" leaves the operator to work out where
    they are in a chain of twelve. Showing the chain, and which link is the
    next one they can actually act on, is the difference between a page that
    blocks and a page that directs.
    """
    by_id = {sp["id"]: sp for sp in state["steps"]}
    # Walk back through the prerequisites to the first thing that is runnable.
    chain, seen, queue = [], set(), list(spec["requires"])
    while queue:
        sid = queue.pop(0)
        if sid in seen:
            continue
        seen.add(sid)
        need = by_id[sid]
        chain.append(need)
        if need["status"] != "done":
            queue.extend(need["requires"])
    chain.sort(key=lambda sp: sp["id"])

    actionable = next((sp for sp in chain if sp["status"] == "ready"), None)
    rows = [[H.esc(f"{sp['id']:02d}"),
             H.esc(sp["title"]),
             H.badge("done", "ok") if sp["status"] == "done"
             else H.badge("do this next", "accent") if sp is actionable
             else H.badge(sp["status"], "pending"),
             f"<a class='btn ghost sm' href='/step/{sp['id']}'>Open</a>"
             if sp["status"] != "locked" else ""]
            for sp in chain]

    go = (f"<p><a class='btn' href='/step/{actionable['id']}'>"
          f"Go to Step {actionable['id']} &mdash; "
          f"{H.esc(actionable['title'])} &rarr;</a></p>" if actionable else "")

    outstanding = [sp for sp in chain if sp["status"] != "done"]
    lede = (f"{H.plural(len(outstanding), 'step')} stand between you and this "
            f"one." if outstanding else "")

    return H.card(
        "This step is locked", H.note(lede)
        + H.table(["#", "What has to happen first", "State", ""], rows) + go,
        anchor="locked",
        hint="Every step declares what it needs, so an action attempted out "
             "of order fails by name rather than quietly producing a "
             "meaningless result. That ordering is what makes the comparison "
             "in Step 5 a prediction instead of a fit.")


def _page_extras(pipeline, step: int, query: Dict[str, str]) -> Dict[str, Any]:
    """Anything a page needs that is not in the pipeline state payload."""
    extra: Dict[str, Any] = {"query": query, "catalogue": None, "twin": None,
                             "record": None, "report": None}
    if step == 1:
        extra["catalogue"] = pipeline.catalogue()
    if step == 3 and query.get("twin"):
        try:
            extra["twin"] = pipeline.twin_detail(query["twin"])
        except StepError:
            extra["twin"] = None
    if step in (8, 10) and query.get("report"):
        extra["report"] = next(
            (r for r in pipeline.reports
             if r["update_id"] == query["report"]), None)
    if step == 10 and query.get("record"):
        rec = pipeline.quarantine.get(query["record"])
        extra["record"] = rec.as_dict() if rec is not None else None
        if rec is not None and rec.analysis:
            extra["record"]["analysis"] = rec.analysis
    return extra


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------
@router.get("/reset", response_class=HTMLResponse)
async def reset_confirm(request: Request):
    """Ask first.  With no JavaScript there is no dialog to lean on."""
    pipeline, lock = _ctx()
    async with lock:
        state = await asyncio.to_thread(pipeline.state)
    resume = next((s["id"] for s in state["steps"]
                   if s["status"] != "done"), 1)
    body = H.card(
        "Discard this session?",
        H.row(
            H.form("/reset", "Yes, reset to Step 1", kind="danger"),
            f"<a class='btn ghost' href='/step/{resume}'>No, keep working</a>"),
        hint="The fleet, the twins, every trained model, the safe pool and the "
             "quarantine are all thrown away. This cannot be undone.")
    return HTMLResponse(H.plain_page(
        title_text="Reset the console", body=body, eyebrow="Session",
        lede="Start again from an empty network.",
        user=getattr(request.state, "user", None)))


@router.post("/reset")
async def reset_do(request: Request):
    from . import api
    _audit(request, "reset", "session discarded")
    async with api.LOCK:
        api.PIPELINE = await asyncio.to_thread(type(api.PIPELINE),
                                               SETTINGS.seed)
    reset_view()
    return RedirectResponse("/step/1", status_code=303)


# ===========================================================================
# STEP 1 -- the IoT environment
# ===========================================================================
def _step1(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    if state.get("source_mode") is None:
        return H.card(
            "Choose a telemetry source first",
            "<p>Before any device is deployed, the console needs to know "
            "whether it is reading a simulated fleet or real peripherals "
            "attached to this machine.</p>"
            "<p><a class='btn' href='/start'>Choose the source &rarr;</a></p>",
            hint="Everything after that decision is identical.")
    if state.get("is_live"):
        return _step1_live(state, extra)
    return _step1_simulated(state, extra)


def _step1_live(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    """Enrol real USB peripherals attached to this machine."""
    usb = state.get("usb") or {}
    enrolled = {d["device_id"] for d in state["devices"]}
    present = usb.get("present") or []

    scan = H.card(
        "Attached USB devices",
        H.row(H.form("/step/1/scan", "Scan the USB bus", inline=True))
        + (H.note(usb.get("error")) if usb.get("error") else "")
        + H.note(f"{H.plural(len(present), 'device')} attached. Enumeration "
                 f"costs about a second, so it runs only when you ask — "
                 f"plug something in and scan again."),
        hint="Read straight off Windows PnP. Enrol a device and the twelve "
             "steps monitor it exactly as they would a simulated one.",
        aside=H.badge(f"{usb.get('refreshes', 0)} scans", "pending"))

    rows = []
    for d in present:
        already = d["slug"] in enrolled
        type_pick = H.select("device_type", "Monitor as",
                             [(t, H.human(t)) for t in DEVICE_TYPES],
                             d["archetype"])
        action = (H.badge("enrolled", "ok") if already else H.form(
            "/step/1/enrol", "Enrol", fields={"slug": d["slug"]},
            body=type_pick, inline=True))
        status_cell = (H.badge(d["status"], "ok") if d["healthy"]
                       else H.badge(d["status"], "attack"))
        if not d["healthy"] and d.get("reason"):
            # "Error" alone sends an operator hunting for a fault that may not
            # exist -- a camera behind a privacy shutter reports it too.
            status_cell += f"<br><small>{H.esc(d['reason'])}</small>"
        rows.append([
            f"<b>{H.esc(d['name'])}</b><br><small>{H.esc(d['instance_id'])}</small>",
            H.esc(d["pnp_class"]),
            status_cell,
            H.esc(f"{d['vid']}:{d['pid']}" if d["vid"] else "--"),
            H.esc(d["reconnects"]),
            H.num(d["present_for_s"], 0) + "s",
            action,
        ])
    picker = H.table(
        ["Device", "Class", "Windows status", "VID:PID", ("Reconnects", "num"),
         ("Attached for", "num"), ""], rows) or H.empty(
        "Nothing found on the USB bus. Plug a device in and scan again.")

    monitored = []
    for d in state["devices"]:
        monitored.append([
            f"<code>{H.esc(d['device_id'])}</code>",
            H.esc(d.get("label") or ""),
            H.esc(H.human(d["device_type"])),
            H.esc(d["sequence"]),
            (H.badge(H.human(d["attack"]), "attack") if d["compromised"]
             else H.badge("Healthy", "ok")),
            H.form("/step/1/remove", "Remove",
                   fields={"device_id": d["device_id"]}, kind="ghost sm",
                   inline=True),
        ])
    fleet = H.table(
        ["Device ID", "Hardware", "Monitored as", ("Samples", "num"),
         "State", ""], monitored) or H.empty(
        "No device enrolled yet. Pick one from the list above.")

    caveat = H.card(
        "What is measured, and what is assumed",
        "<p>Ten of the sixteen features are measured from <b>this host</b>: "
        "CPU, memory, throughput, packet rate, the connection table. Three are "
        "measured from <b>the peripheral itself</b>: how long it has been "
        "attached, how often it dropped and came back, and whether Windows "
        "still considers it healthy. Bus power is <b>declared</b> by the USB "
        "specification for its class, not measured.</p>"
        "<p>Two cannot be obtained on this machine at all. "
        "<code>failed_logins</code> needs the Windows Security event log and "
        "administrator rights; <code>payload_entropy</code> needs a packet "
        "capture driver. Both are held at zero and reported as missing, never "
        "invented.</p>"
        "<p>Attributing the host's network activity to the selected "
        "peripheral is a <b>modelling assumption</b>, not a per-device "
        "measurement — a USB webcam has no network stack of its own, and "
        "a compromised one would exfiltrate through its host's.</p>",
        hint="Stated here because it is the first question a reviewer will "
             "ask, and the honest answer is more interesting than a vague one.")

    return scan + picker + H.card("Monitored devices", fleet) + caveat


def _step1_simulated(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    counts = state["fleet"]["layout"] or {}
    cards = []
    for d in extra["catalogue"] or []:
        baseline = "".join(
            f"<span>{H.esc(k.replace('_', ' '))} <b>{H.esc(v)}</b></span>"
            for k, v in list(d["baseline"].items())[:6])
        cards.append(
            f"<article class='pick'>"
            f"<h3>{H.esc(d['label'])}</h3>"
            f"<p class='deployed'>{counts.get(d['type'], 0)} deployed"
            f" &middot; suggested {d['suggested']}</p>"
            f"<p>{H.esc(d['blurb'])}</p>"
            f"<div class='baseline'>{baseline}</div>"
            f"{H.tags(d['typical_threats'])}"
            + H.form("/step/1/add", "Add device",
                     fields={"device_type": d["type"]}, inline=True)
            + "</article>")

    rows = []
    for d in state["devices"]:
        state_cell = (H.badge(H.human(d["attack"]), "attack")
                      if d["compromised"] else H.badge("Healthy", "ok"))
        rows.append([
            f"<code>{H.esc(d['device_id'])}</code>",
            H.esc(H.human(d["device_type"])),
            H.esc(d["sequence"]),
            state_cell,
            H.form("/step/1/remove", "Remove",
                   fields={"device_id": d["device_id"]}, kind="ghost sm",
                   inline=True),
        ])

    deployed = H.table(
        ["Device ID", "Type", ("Ticks", "num"), "State", ""], rows
    ) or H.empty("No devices deployed yet. Add at least two from the "
                 "catalogue above.")

    return (
        H.card("Device catalogue",
               f"<div class='picks'>{''.join(cards)}</div>",
               hint="Each type has a genuinely different behavioural "
                    "fingerprint. The mix chosen here determines what the "
                    "detector is trained on later, so a network of bulbs and "
                    "sensors produces a very different model from one with "
                    "three cameras in it.")
        + H.card("Deployed network",
                 deployed,
                 hint=f"{H.plural(len(state['devices']), 'device')} on the "
                      f"network. At least two are needed before the gateway "
                      f"will start."))


# ===========================================================================
# STEP 2 -- edge gateway
# ===========================================================================
def _step2(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    g = state["gateway"]
    gateway = H.card(
        "Edge gateway",
        H.form("/step/2/start",
               "Gateway running" if g["online"] else "Start gateway",
               disabled=g["online"],
               because="The gateway is already up; there is nothing to start."),
        hint="The gateway runs on the local network. Nothing is sent to a "
             "cloud, which matters for more than latency: a consumer network "
             "that depends on a vendor cloud for security inherits that "
             "vendor's compromise.",
        aside=H.badge("Online", "ok") if g["online"]
        else H.badge("Offline", "pending"))

    collect = H.card(
        "Collect telemetry",
        H.form("/step/2/collect", "Collect",
               body=H.controls(H.field("ticks", "Ticks to collect",
                                       _fv(2, "ticks", 45), min=1, max=400)),
               disabled=not g["online"],
               because="Start the edge gateway first -- nothing collects "
                       "until it is online.")
        + H.metrics([
            ("Total ticks", state["stats"]["ticks"]),
            ("Observations", state["stats"]["observations"]),
            ("Buffered batches", g["buffered_batches"], "awaiting the twins",
             "accent" if g["buffered_batches"] else ""),
            ("Fed to twins", g["fed_batches"]),
        ]),
        hint="Devices emit data only when you ask for a tick. One tick "
             "produces one observation from every device.")

    last = VIEW.last.get("2/collect", {})
    latest = last.get("latest") or []
    live = bool(state.get("is_live"))
    unavailable = _unavailable_features(state) if live else set()

    recent = ""
    if latest:
        def cell(r, name, digits):
            # In live mode an unobtainable feature reads zero, and a bare zero
            # is indistinguishable from a genuine measurement of nothing.
            if name in unavailable:
                return "<small>n/a</small>"
            return H.num(r["features"][name], digits)

        rows = [[f"<code>{H.esc(r['device_id'])}</code>",
                 cell(r, "cpu_usage", 1), cell(r, "net_out_kbps", 1),
                 cell(r, "packet_rate", 0), cell(r, "conn_attempts", 0),
                 cell(r, "failed_logins", 0), cell(r, "port_diversity", 0)]
                for r in latest]
        recent = H.card("Most recent tick", H.table(
            ["Device", ("CPU %", "num"), ("Net out kb/s", "num"),
             ("Packets/s", "num"), ("Conns", "num"),
             ("Failed logins", "num"), ("Ports", "num")], rows),
            hint=("Raw telemetry exactly as it arrived at the gateway. "
                  "Columns reading n/a cannot be obtained on this host and "
                  "are held at zero rather than invented."
                  if live else
                  "Raw telemetry exactly as it arrived at the gateway."))

    return gateway + collect + recent + _readings_card(state, latest)


def _unavailable_features(state: Dict[str, Any]) -> set:
    rows = (state.get("live_support") or {}).get("rows") or []
    return {r["feature"] for r in rows if r["provenance"] == "unavailable"}


def _readings_card(state: Dict[str, Any],
                   latest: List[Dict[str, Any]]) -> str:
    """Every one of the sixteen readings, and where each one came from.

    The question this answers is the one a reviewer asks first: *how do I know
    these came off real hardware?*  Showing seven selected columns does not
    answer it, and showing a zero for a feature that cannot be measured at all
    actively misleads.  So in live mode the console puts the whole vector on
    screen, each value next to its provenance, for the tick that just arrived.
    """
    if not state.get("is_live") or not latest:
        return ""

    meta = {r["feature"]: r
            for r in (state.get("live_support") or {}).get("rows") or []}
    if not meta:
        return ""

    tone = {"host": "accent", "device": "ok",
            "declared": "warn", "unavailable": "bad"}
    shown = latest[:4]

    columns: List[Any] = ["Feature", "Provenance"]
    for r in shown:
        label = next((d.get("label") or d["device_id"]
                      for d in state["devices"]
                      if d["device_id"] == r["device_id"]), r["device_id"])
        columns.append((label[:22], "num"))
    columns.append("How it is obtained")

    rows = []
    for feature, info in meta.items():
        prov = info["provenance"]
        cells = [f"<code>{H.esc(feature)}</code>", H.badge(prov, tone.get(prov, ""))]
        for r in shown:
            value = r["features"].get(feature)
            cells.append("<small>n/a</small>" if prov == "unavailable"
                         else H.num(value, 2))
        cells.append(f"<small>{H.esc(info['how'])}</small>")
        rows.append(cells)

    counts: Dict[str, int] = {}
    for info in meta.values():
        counts[info["provenance"]] = counts.get(info["provenance"], 0) + 1

    body = H.metrics([
        ("From this host", counts.get("host", 0), "network and resource planes"),
        ("From the device", counts.get("device", 0), "presence and stability", "ok"),
        ("Declared", counts.get("declared", 0), "USB spec, not measured", "warn"),
        ("Unavailable", counts.get("unavailable", 0), "held at zero, flagged",
         "bad" if counts.get("unavailable") else ""),
    ]) + H.table(columns, rows)

    return H.card(
        "Every reading in this tick", body,
        anchor="every-reading",
        hint="The complete sixteen-feature vector for the tick just collected, "
             "with the provenance of each value. Cross-check any host row "
             "against Task Manager while a collection runs: the figures move "
             "together because they come from the same counters.")


# ===========================================================================
# STEP 3 -- holographic twins
# ===========================================================================
def _step3(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    min_fit = state["constants"]["twin_min_fit"]
    buffered = state["gateway"]["buffered_batches"]

    build = H.card(
        "Create and feed twins",
        H.row(H.form("/step/3/create", "Create twins", inline=True),
              H.form("/step/3/feed",
                     f"Feed {H.plural(buffered, 'buffered batch', 'buffered batches')}",
                     kind="ghost", disabled=not buffered, inline=True,
                     because="Nothing is buffered. Collect telemetry in "
                             "Step 2, then feed it."))
        + H.note(f"{state['twins']['ready']}/{state['twins']['count']} twins "
                 f"have the {min_fit} observations their predictor needs."),
        hint="A twin is not a copy of the device. It is a model of what that "
             "specific unit considers normal, held as five separate "
             "projections -- resource, network, access, topology, actuation -- "
             "rather than one blob.")

    twins = [d for d in state["devices"] if d["twin_exists"]]
    rows = []
    for d in twins:
        progress = min(1.0, (d["twin_observations"] or 0) / max(min_fit, 1))
        rows.append([
            f"<code>{H.esc(d['device_id'])}</code>",
            H.esc(H.human(d["device_type"])),
            H.esc(d["twin_observations"] or 0),
            H.bar(progress, "ok" if progress >= 1 else "warn"),
            H.badge("Ready", "ok") if d["twin_ready"]
            else H.badge("Warming", "pending"),
            f"<a class='btn ghost sm' "
            f"href='/step/3?twin={H.esc(d['device_id'])}'>Inspect</a>",
        ])
    status = H.card("Twin status", H.table(
        ["Twin", "Type", ("Observations", "num"), "Readiness", "State", ""],
        rows)) if rows else H.empty("No twins yet. Create them above.")

    return build + status + _twin_detail(extra.get("twin"))


def _twin_detail(twin: Optional[Dict[str, Any]]) -> str:
    if not twin:
        return ""
    baseline = twin.get("baseline") or {}
    rows = [[H.esc(k.replace("_", " ")), H.num(v, 3)]
            for k, v in list(baseline.items())]
    planes = twin.get("plane_deviation") or {}
    plane_rows = [[H.esc(H.human(k)), H.num(v, 3),
                   H.badge("anomalous", "attack")
                   if k in (twin.get("anomalous_planes") or [])
                   else H.badge("normal", "ok")]
                  for k, v in planes.items()]
    return H.card(
        f"Twin — {twin['device_id']}",
        H.metrics([
            ("Observations", twin["observations"]),
            ("In history", twin["history"]),
            ("Refused by trust gate", twin["rejected"], "hostile ticks",
             "accent" if twin["rejected"] else ""),
            ("Last consistency", H.num(twin.get("last_consistency"), 4)),
        ])
        + (H.table(["Plane", ("Deviation (sigma)", "num"), "State"],
                   plane_rows) if plane_rows else "")
        + H.table(["Feature", ("Learned baseline", "num")], rows)
        + "<p><a class='btn ghost sm' href='/step/3'>Close</a></p>",
        hint="The learned per-feature norm, and the per-plane deviation of the "
             "most recent scored observation.")


# ===========================================================================
# STEP 4 -- forward prediction
# ===========================================================================
def _step4(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    fit = H.card(
        "Fit the forward models",
        H.form("/step/4/fit", "Fit predictors"),
        hint="Each twin fits a ridge vector-autoregression over its own recent "
             "history. A closed-form fit takes microseconds and its residual "
             "spread gives the width of the future cone for free, which is "
             "what a point-estimate neural forecaster could not do here.")

    last = VIEW.last.get("4/fit", {})
    out = [fit]
    if last.get("predictions"):
        out.append(H.note(
            f"{H.plural(len(last['fitted']), 'predictor')} fitted over "
            f"{last.get('lags')} autoregressive lags."))
        for pred in last["predictions"]:
            rows = [[H.esc(c["feature"].replace("_", " ")),
                     H.num(c["current"], 2), H.num(c["predicted"], 2),
                     H.num(c["predicted"] - c["current"], 2)]
                    for c in pred["compare"]]
            out.append(H.card(
                f"{pred['device_id']}",
                H.table(["Feature", ("Now", "num"), ("Predicted next", "num"),
                         ("Delta", "num")], rows),
                hint=f"{H.human(pred['device_type'])} · "
                     f"{pred['observations']} observations · "
                     f"{pred['fit_rows']} rows used in the fit"))
    return "".join(out)


# ===========================================================================
# STEP 5 -- counterfactual futures
# ===========================================================================
def _step5(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    generate = H.card(
        "Commit to counterfactual futures",
        H.form("/step/5/futures", "Generate and commit futures",
               body=H.controls(
                   H.field("n_futures", "Futures per twin",
                           _fv(5, "n_futures", SETTINGS.twin.n_futures),
                           min=3, max=80),
                   H.field("horizon", "Ticks ahead",
                           _fv(5, "horizon", SETTINGS.twin.horizon),
                           min=1, max=20))),
        hint="These are the behaviours that would follow if each device "
             "carried on being itself. They are committed now, before the "
             "observation that will judge them exists -- which is the only "
             "thing that makes the comparison a prediction rather than a fit.")

    out = [generate]
    futures = VIEW.last.get("5/futures", {})
    detail = futures.get("detail") or {}
    if detail.get("armed"):
        rows = [[H.esc(f["feature"].replace("_", " ")), H.num(f["mean"], 2),
                 H.num(f["sd"], 2), H.num(f["low"], 2), H.num(f["high"], 2)]
                for f in detail["features"]]
        out.append(H.card(
            f"Committed futures — {futures.get('detail_device', '')}",
            H.metrics([("Futures", detail["n_futures"]),
                       ("Horizon", f"{detail['horizon']} ticks"),
                       ("Committed at observation",
                        detail["at_observation"])])
            + H.table(["Feature", ("Mean", "num"), ("Spread", "num"),
                       ("Lowest", "num"), ("Highest", "num")], rows),
            hint="The cone of next-tick behaviour this twin is prepared to "
                 "accept as ordinary. A steady sensor gets a tight cone, a "
                 "bursty speaker a wide one."))

    check = H.card(
        "Score reality against the commitment",
        H.form("/step/5/check", "Take one live tick and score it",
               disabled=state["twins"]["armed"] == 0,
               because="No twin has committed futures yet. Generate them "
                       "above first -- the futures have to exist before the "
                       "observation they judge."),
        hint=f"One tick is collected and compared with the futures already "
             f"committed. Anything scoring under "
             f"{state['constants']['obs_threshold']} is twin-flagged and "
             f"refused entry to the twin's notion of normal.")
    out.append(check)

    scored = VIEW.last.get("5/check", {})
    if scored.get("rows"):
        rows = []
        for r in scored["rows"]:
            rows.append([
                f"<code>{H.esc(r['device_id'])}</code>",
                H.esc(H.human(r["ground_truth"])),
                H.num(r["consistency"], 4),
                H.num(r["deviation"], 2),
                H.badge("flagged", "attack") if r["flagged"]
                else H.badge("consistent", "ok"),
                H.esc(", ".join(H.human(p) for p in r["anomalous_planes"])
                      or "--"),
            ])
        out.append(H.card(
            "Consistency of the live tick",
            H.table(["Device", "Ground truth", ("Consistency", "num"),
                     ("Deviation (sigma)", "num"), "Verdict",
                     "Anomalous planes"], rows),
            hint=f"{scored['flagged']} of {len(scored['rows'])} observations "
                 f"fell below the {scored['threshold']} flag threshold."))
    return "".join(out)


# ===========================================================================
# STEP 6 -- threat detection
# ===========================================================================
def _step6(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    out = []

    corpus = state.get("corpus")
    corpus_body = H.form(
        "/step/6/corpus", "Build labelled corpus",
        body=H.controls(H.field("rows_per_class", "Rows per class",
                                _fv(6, "rows_per_class", 380),
                                min=80, max=1200)))
    if corpus:
        corpus_body += H.metrics([
            ("Total rows", corpus["rows"]),
            ("Training", corpus["train_rows"]),
            ("Evaluation", corpus["eval_rows"]),
            ("Trusted core", corpus["core_rows"]),
            ("Held-out pool", corpus["pool_rows"]),
            ("Built in", f"{corpus['elapsed_s']}s"),
        ])
    out.append(H.card(
        "Training corpus", corpus_body,
        hint="Generated from the profiles of the fleet you actually deployed, "
             "across a range of attack intensities. Training only on loud "
             "attacks produces a model that is perfect in a demo and blind to "
             "anything subtle."))

    train_body = H.form("/step/6/train", "Train the detector",
                        disabled=corpus is None,
                        because="Build the labelled corpus first; there is "
                                "nothing to train on.")
    trained = VIEW.last.get("6/train", {})
    if trained.get("metrics"):
        m = trained["metrics"]
        train_body += H.metrics([
            ("Accuracy", H.pct(m["accuracy"]), "", H.tone_for(m["accuracy"], 0.9, 0.8)),
            ("Macro F1", H.pct(m["macro_f1"])),
            ("False positives", H.pct(m["false_positive_rate"]),
             "benign called hostile"),
            ("False negatives", H.pct(m["false_negative_rate"]),
             "attack called benign"),
            ("Model", f"v{trained['version']}"),
            ("Trained in", f"{trained['elapsed_s']}s"),
        ])
        per_class = [[H.esc(H.human(k)), H.esc(v["support"]),
                      H.pct(v["recall"]) if v["recall"] is not None else "--",
                      H.bar(v["recall"] or 0,
                            H.tone_for(v["recall"] or 0, 0.9, 0.75))]
                     for k, v in m["per_class"].items()]
        train_body += H.table(["Class", ("Support", "num"), ("Recall", "num"),
                               ""], per_class)
        imp = [[H.esc(i["feature"]), H.num(i["importance"], 4)]
               for i in trained.get("importances", [])]
        train_body += H.table(["Most informative feature",
                               ("Importance", "num")], imp)
    out.append(H.card("Edge threat detector", train_body,
                      hint="A random forest, chosen because it retrains from "
                           "scratch in a second -- which is what makes the "
                           "self-healing rollback in Step 12 possible at all."))

    devices = [(d["device_id"], d["device_id"]) for d in state["devices"]]
    attack_body = H.form(
        "/step/6/attack", "Launch attack", kind="danger",
        body=H.controls(
            H.select("device_id", "Target device", devices,
                     _fv(6, "device_id", state.get("selected_device"))),
            H.select("attack", "Attack class",
                     [(a, H.human(a)) for a in ATTACK_CLASSES],
                     _fv(6, "attack", "ddos")),
            H.field("duration", "Ticks", _fv(6, "duration", 15),
                    min=1, max=400),
            H.field("intensity", "Intensity", _fv(6, "intensity", 1.0),
                    min=0.05, max=1.0, step=0.05)),
        disabled=not devices,
        because="No device is deployed. Add one in Step 1.")
    live = [d for d in state["devices"] if d["compromised"]]
    if live:
        rows = [[f"<code>{H.esc(d['device_id'])}</code>",
                 H.badge(H.human(d["attack"]), "attack"),
                 H.esc(f"{d['attack_ticks_left']}/{d['attack_total']}"),
                 H.num(d["intensity"], 2),
                 H.form("/step/6/stop", "Stop",
                        fields={"device_id": d["device_id"]},
                        kind="ghost sm", inline=True)]
                for d in live]
        attack_body += H.table(["Device", "Attack", ("Ticks left", "num"),
                                ("Intensity", "num"), ""], rows)
    out.append(H.card("Launch an attack by hand", attack_body,
                      hint="Nothing turns hostile on its own. Every attack in "
                           "this build is started here, against a device you "
                           "name, at an intensity you choose."))

    monitor_body = H.form(
        "/step/6/monitor", "Monitor",
        body=H.controls(H.field("ticks", "Ticks to monitor",
                                _fv(6, "ticks", 5), min=1, max=60)),
        disabled=state.get("model") is None,
        because="Train the detector first; monitoring needs a model to "
                "classify with.")
    mon = VIEW.last.get("6/monitor", {})
    if mon.get("all_rows"):
        rows = []
        for r in mon["all_rows"][-24:][::-1]:
            rows.append([
                f"<code>{H.esc(r['device_id'])}</code>",
                H.esc(H.human(r["ground_truth"])),
                H.badge(H.human(r["predicted"]),
                        "ok" if r["predicted"] == "normal" else "attack"),
                H.pct(r["confidence"], 0),
                H.num(r["consistency"], 3),
                H.badge("flagged", "attack") if r["twin_flagged"]
                else H.badge("quiet", "pending"),
                H.badge("correct", "ok") if r["correct"]
                else H.badge("wrong", "bad"),
            ])
        monitor_body += H.table(
            ["Device", "Ground truth", "Model verdict", ("Confidence", "num"),
             ("Twin consistency", "num"), "Twin", "Outcome"], rows)
    out.append(H.card("Live protection loop", monitor_body,
                      hint="One deliberate pass of the gateway: the twin "
                           "scores each observation against its commitment, "
                           "the model classifies it, and the self-healing "
                           "monitor records whether the two agreed."))
    return "".join(out)


# ===========================================================================
# STEP 7 -- craft a poisoned contribution
# ===========================================================================
def _step7(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    options = [(s, STRATEGY_TEXT.get(s, {}).get("label", H.human(s)),
                STRATEGY_TEXT.get(s, {}).get("detail", ""))
               for s in POISON_STRATEGIES]
    craft = H.card(
        "Craft a training contribution",
        H.form("/step/7/craft", "Craft update",
               body=H.radio_cards("strategy", options,
                                  _fv(7, "strategy", "label_flip"))
               + H.controls(
                   H.field("rows", "Rows", _fv(7, "rows", 240),
                           min=40, max=1500),
                   H.field("potency", "Potency", _fv(7, "potency", 1.0),
                           min=0.05, max=1.0, step=0.05))),
        hint="The update lands in the inbox and touches nothing. It is not "
             "scored until you validate it in Step 8, and not applied to the "
             "system until you apply it.")

    rows = []
    for u in state["inbox"]:
        labels = ", ".join(f"{H.human(k)} {v}"
                           for k, v in u["labels"].items())
        verdict = "--"
        if u.get("decision"):
            verdict = (H.badge(u["decision"].title(),
                               "ok" if u["decision"] == "ACCEPTED" else "attack")
                       + f" <small>CCS {H.num(u['consistency_score'], 3)}</small>")
        rows.append([
            f"<code>{H.esc(u['update_id'])}</code>",
            H.esc(u["source"]),
            H.esc(u["n_samples"]),
            f"<small>{H.esc(labels)}</small>",
            H.badge(u["state"].replace("applied:", ""), "pending"),
            verdict,
            H.form("/step/7/discard", "Discard",
                   fields={"update_id": u["update_id"]}, kind="ghost sm",
                   inline=True) if not u["applied"] else "",
        ])
    inbox = H.card(
        "Inbox",
        H.table(["Update", "Source", ("Rows", "num"), "Label mix", "State",
                 "Verdict", ""], rows)
        or H.empty("Nothing in the inbox. Craft an update above."),
        hint=f"{H.plural(len(state['inbox']), 'update')} waiting. Sybil "
             f"splits its payload across many small updates, so one craft can "
             f"produce several rows here.",
        aside="<a class='btn' href='/step/8'>Validate in Step 8 &rarr;</a>"
        if state["inbox"] else "")
    return craft + inbox


# ===========================================================================
# STEP 8 -- counterfactual validation
# ===========================================================================
def _step8(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    bank = state["bank"]
    val = state["validator"]
    cal = val.get("calibration") or {}

    prep_body = H.row(
        H.form("/step/8/bank", "Rebuild audit bank", kind="ghost", inline=True),
        H.form("/step/8/calibrate", "Calibrate the gate", inline=True,
               body=H.field("honest_updates", "Honest updates",
                            _fv(8, "honest_updates", 8), min=3, max=20)))
    prep_body += H.metrics([
        ("Bank scenarios", bank["n"]),
        ("Attack-conditioned", bank["attack"]),
        ("Benign", bank["benign"]),
        ("Accept threshold", H.num(val["threshold"], 4), "calibrated"
         if cal.get("calibrated") else "fallback",
         "accent" if cal.get("calibrated") else "warn"),
    ])
    if cal.get("calibrated"):
        prep_body += H.kv_list([
            ("Honest mean CCS", H.num(cal["honest_mean"], 4)),
            ("Honest spread", H.num(cal["honest_std"], 4)),
            ("Spread used (floored)", H.num(cal["spread_used"], 4)),
            ("z", cal["z"]),
            ("Raw threshold", H.num(cal["raw_threshold"], 4)),
            ("Clipped to", H.num(cal["threshold"], 4)),
        ])
    out = [H.card(
        "The audit bank and the gate", prep_body,
        hint="The bank is the twins' committed futures, half left benign and "
             "half deformed by each attack class. The accept threshold is not "
             "a constant: it is mean(honest) minus z times spread, measured on "
             "this fleet.")]

    rows = []
    for u in state["inbox"]:
        if u["applied"]:
            continue
        validated = u.get("decision") is not None
        actions = []
        if not validated:
            actions.append(H.form("/step/8/validate", "Validate",
                                  fields={"update_id": u["update_id"]},
                                  inline=True))
        else:
            actions.append(H.form(
                "/step/8/apply", f"Apply ({u['decision'].title()})",
                fields={"update_id": u["update_id"]}, inline=True))
            opposite = ("QUARANTINED" if u["decision"] == "ACCEPTED"
                        else "ACCEPTED")
            actions.append(H.form(
                "/step/8/apply", f"Override to {opposite.title()}",
                fields={"update_id": u["update_id"], "override": opposite},
                kind="ghost sm", inline=True))
            actions.append(
                f"<a class='btn ghost sm' href='/step/8?report="
                f"{H.esc(u['update_id'])}'>Report</a>")
        rows.append([
            f"<code>{H.esc(u['update_id'])}</code>",
            H.esc(u["source"]),
            H.esc(u["n_samples"]),
            H.num(u["consistency_score"], 4) if validated else "--",
            H.num(u["threshold"], 4) if validated else "--",
            H.badge(u["decision"].title(),
                    "ok" if u["decision"] == "ACCEPTED" else "attack")
            if validated else H.badge("pending", "pending"),
            H.row(*actions),
        ])
    out.append(H.card(
        "Updates awaiting a decision",
        H.table(["Update", "Source", ("Rows", "num"), ("CCS", "num"),
                 ("Gate", "num"), "Decision", ""], rows)
        or H.empty("Nothing to validate. Craft an update in Step 7."),
        hint="Validation applies nothing. The verdict is a recommendation "
             "until you apply it, and you may overrule it in either "
             "direction -- a control a human cannot countermand is not a "
             "control, it is an oracle."))

    report = extra.get("report") or VIEW.last.get("8/validate", {}).get("report")
    if report:
        out.append(_report_card(report))
    return "".join(out)


def _report_card(r: Dict[str, Any]) -> str:
    e = r.get("evidence") or {}
    weights = e.get("weights") or {}
    contributions = e.get("contributions") or {}
    passed = r["decision"] == "ACCEPTED"

    labels = {
        "attack_agreement": "Attack agreement",
        "benign_agreement": "Benign agreement",
        "stability": "Stability",
        "plane_coherence": "Plane coherence",
        "label_integrity": "Label integrity",
        "label_agreement": "Label agreement",
    }
    comp_rows = []
    for key, label in labels.items():
        value = e.get(key, 0.0)
        comp_rows.append([
            H.esc(label),
            H.num(value, 4),
            H.bar(value, H.tone_for(value)),
            H.num(weights.get(key), 2),
            H.num(contributions.get(key), 4),
        ])

    per_class = [[H.esc(H.human(k)), H.pct(v, 0),
                  H.bar(v, H.tone_for(v, 0.9, 0.75))]
                 for k, v in (e.get("bank_per_class") or {}).items()]
    strategies = sorted((e.get("strategy_scores") or {}).items(),
                        key=lambda kv: -kv[1])
    strat_rows = [[H.esc(H.human(k)), H.num(v, 4), H.bar(v, "accent")]
                  for k, v in strategies]
    agreement = e.get("agreement_detail") or {}

    body = H.metrics([
        ("CCS", H.num(r["consistency_score"], 4), "weighted sum of six",
         "ok" if passed else "bad"),
        ("Gate", H.num(r["threshold"], 4), "calibrated on this fleet"),
        ("Margin", f"{e.get('margin', 0):+.4f}",
         "distance from the threshold"),
        ("Decision", r["decision"].title(), "", "ok" if passed else "attack"),
        ("Suspected", H.human(r["suspected_strategy"]),
         f"confidence {H.pct(r['strategy_confidence'], 0)}"),
        ("Really was", H.human(r["declared_strategy"]), "simulator ground truth"),
    ])
    body += H.table(["Component", ("Value", "num"), "", ("Weight", "num"),
                     ("Contribution", "num")], comp_rows)
    body += H.kv_list([
        ("Bank scenarios tested", e.get("bank_n")),
        ("Label shift (total variation)", H.num(e.get("label_shift"), 4)),
        ("Normal excess", H.num(e.get("normal_excess"), 4)),
        ("Repeat concentration", H.num(e.get("repeat_score"), 4)),
        ("Most repeated feature", e.get("repeat_feature") or "--"),
        ("Labels vs incumbent (pooled)", H.num(agreement.get("pooled"), 4)),
        ("Benign-ward disagreement", H.num(agreement.get("benign_ward"), 4)),
        ("Attack-ward disagreement", H.num(agreement.get("attack_ward"), 4)),
        ("Source reputation", H.num(r.get("reputation"), 4)),
        ("New source", "yes" if e.get("new_source") else "no"),
        ("Novelty penalty", H.num(e.get("novelty_penalty"), 2)),
        ("Scored in", f"{e.get('elapsed_ms')} ms"),
    ])
    if per_class:
        body += ("<h4>What the shadow model would still catch</h4>"
                 + H.table(["Bank class", ("Still detected", "num"), ""],
                           per_class))
    if strat_rows:
        body += ("<h4>Strategy attribution</h4>"
                 + H.table(["Strategy", ("Score", "num"), ""], strat_rows)
                 + H.note("Rule-based on purpose: a learned attributor would "
                          "need labelled poison to train on, and if we had "
                          "that we would not need the defence. Every score is "
                          "shown so you can disagree."))
    return H.card(
        f"Validation report — {r['update_id']}", body,
        anchor="validation-report",
        hint=f"Source {r['source']} · {r['n_samples']} rows. The update "
             f"was grafted onto the trusted core, a shadow model trained, and "
             f"that shadow put in front of futures the twins committed to "
             f"before this update existed.",
        aside=H.badge(r["decision"].title(), "ok" if passed else "attack"))


# ===========================================================================
# STEP 9 -- predictive immunization
# ===========================================================================
def _step9(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    chosen = _fv(9, "vaccines", "boundary,relabel,trigger")
    chosen_list = chosen.split(",") if isinstance(chosen, str) else chosen

    body = H.form(
        "/step/9/vaccine", "Generate vaccines",
        body=H.checkboxes("vaccines", VACCINES, chosen_list)
        + H.controls(H.field(
            "scenarios", "Scenarios per strategy",
            _fv(9, "scenarios", SETTINGS.immune.scenarios_per_strategy),
            min=7, max=200)))
    vac = VIEW.last.get("9/vaccine", {}).get("vaccine") or {}
    if vac.get("rows"):
        body += H.metrics(
            [("Vaccine rows", vac["rows"]), ("Generation", vac["generation"])]
            + [(H.human(k), v) for k, v in (vac.get("breakdown") or {}).items()])
        rows = [[H.esc(H.human(k)), H.esc(v)]
                for k, v in (vac.get("classes") or {}).items()]
        body += H.table(["Vaccine class", ("Rows", "num")], rows)
    out = [H.card(
        "Manufacture vaccines from predicted futures", body,
        hint="Boundary hardening trains on weak but genuine attacks so the "
             "benign region cannot be pushed outward. Relabel resistance "
             "makes a contributor claiming floods are normal argue against "
             "the model's own experience. Trigger resistance teaches that "
             "pinning odd constants onto a row does not make it benign -- "
             "without ever using the attacker's actual trigger, which we do "
             "not know.")]

    res_body = H.form("/step/9/resistance", "Rehearse every attack")
    res = VIEW.last.get("9/resistance", {}).get("resistance") or {}
    if res.get("per_strategy"):
        res_body += H.metrics([
            ("Poison resistance", H.num(res["poison_resistance"], 4), "",
             H.tone_for(res["poison_resistance"], 0.85, 0.7)),
            ("Weakest against", H.human(res.get("weakest"))),
            ("Scenarios tested", res.get("scenarios_tested")),
            ("Poison share", H.pct(res.get("poison_share"), 0)),
        ])
        rows = [[H.esc(H.human(k)), H.num(v, 4),
                 H.bar(v, H.tone_for(v, 0.9, 0.78))]
                for k, v in res["per_strategy"].items()]
        res_body += H.table(["Rehearsed strategy",
                             ("Surviving attack recall", "num"), ""], rows)
    out.append(H.card(
        "Measure poison resistance", res_body,
        hint="For each strategy: craft poison from the current pool, graft it "
             "on at a realistic federated share, retrain a probe, and measure "
             "how many bank attack scenarios that probe still catches. The "
             "mean is a promotion gate in Step 11."))
    return "".join(out)


# ===========================================================================
# STEP 10 -- quarantine and analysis
# ===========================================================================
def _step10(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    q = state["quarantine"]
    rows = []
    for rec in q["records"]:
        actions = [
            H.form("/step/10/analyse", "Analyse",
                   fields={"update_id": rec["update_id"]}, inline=True),
        ]
        if not rec["released"]:
            actions.append(H.form(
                "/step/10/release", "Release", kind="ghost sm",
                fields={"update_id": rec["update_id"]}, inline=True))
        rows.append([
            f"<code>{H.esc(rec['update_id'])}</code>",
            H.esc(rec["source"]),
            H.esc(rec["n_samples"]),
            H.num(rec["consistency_score"], 4),
            H.esc(H.human(rec["suspected_strategy"])),
            H.esc(H.human(rec["declared_strategy"])),
            H.badge("released", "ok") if rec["released"]
            else H.badge("held", "attack"),
            H.row(*actions),
        ])

    body = H.metrics([
        ("Held", q["held"]),
        ("Total quarantined", q["total_quarantined"]),
        ("Released", q["total_released"]),
    ])
    body += H.table(["Update", "Source", ("Rows", "num"), ("CCS", "num"),
                     "Suspected", "Really was", "State", ""], rows) \
        or H.empty("Nothing has been quarantined yet.")
    body += H.row(H.form("/step/10/rescore", "Rescore against current bank",
                         kind="ghost", disabled=not q["held"], inline=True,
                         because="Nothing is being held, so there is nothing "
                                 "to rescore."))

    out = [H.card(
        "Quarantine zone", body,
        hint="A quarantined update is held intact with the report that "
             "condemned it, not deleted. The gate that rejected it is only as "
             "good as the bank it was scored against, and the bank improves "
             "every round -- so held updates can be rescored and released.")]

    rescore = VIEW.last.get("10/rescore", {}).get("rescore") or {}
    if rescore:
        out.append(H.card("Rescore result", H.kv_list([
            ("Rescored", rescore.get("rescored")),
            ("Would now pass", ", ".join(rescore.get("would_pass", [])) or "none"),
            ("Still held", ", ".join(rescore.get("still_held", [])) or "none"),
        ])))

    analysis = (VIEW.last.get("10/analyse", {}).get("analysis")
                or ((extra.get("record") or {}).get("analysis")))
    if analysis:
        out.append(_analysis_card(analysis))
    return "".join(out)


def _analysis_card(a: Dict[str, Any]) -> str:
    body = H.metrics([
        ("Suspected", H.human(a["suspected_strategy"]),
         f"confidence {H.pct(a['strategy_confidence'], 0)}"),
        ("Rows", a["n_samples"]),
    ])
    body += "<h4>Findings</h4>" + H.findings(a.get("findings", []))

    comps = a.get("components") or {}
    if comps:
        body += H.table(
            ["Component", ("Value", "num"), ""],
            [[H.esc(H.human(k)), H.num(v, 4), H.bar(v, H.tone_for(v))]
             for k, v in comps.items()])

    rows = a.get("suspicious_rows") or []
    if rows:
        body += "<h4>Most physically inconsistent rows</h4>"
        body += H.table(
            [("Row", "num"), "Declared label", "Worst ratio", ("Sigma", "num"),
             "Features"],
            [[H.esc(r["row"]), H.esc(H.human(r["declared_label"])),
              H.esc(r["worst_ratio"]), H.num(r["sigma"], 2),
              "<small>" + H.esc(", ".join(
                  f"{k} {v}" for k, v in r["features"].items())) + "</small>"]
             for r in rows])
    return H.card(f"Forensic analysis — {a['update_id']}", body,
                  anchor="forensic-analysis", hint=f"Source {a['source']}.")


# ===========================================================================
# STEP 11 -- secure retraining
# ===========================================================================
def _step11(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    rt = state["retrainer"]
    gates = rt["gates"]

    body = H.form(
        "/step/11/retrain", "Retrain and run the gates",
        body=H.select("immunize", "Fold in vaccines",
                      [("yes", "Yes -- immunize while retraining"),
                       ("no", "No -- safe pool only")],
                      _fv(11, "immunize", "yes")))
    body += H.metrics([
        ("Safe pool", rt["pool_size"], f"minimum {rt['min_samples']}",
         "ok" if rt["pool_size"] >= rt["min_samples"] else "warn"),
        ("Accepted updates", rt["accepted_updates"]),
        ("Retrains", rt["retrains"]),
        ("Promotions", rt["promotions"]),
    ])
    if rt["composition"]:
        body += H.table(
            ["Pool contributor", ("Rows", "num"), ("Share", "num")],
            [[H.esc(c["source"]), H.esc(c["rows"]), H.pct(c["share"], 1)]
             for c in rt["composition"]])
    out = [H.card(
        "Retrain on validated data only", body,
        hint="Rows enter the pool only by passing Step 8 or by being released "
             "from quarantine, and every row remembers which update and which "
             "source contributed it -- which is what makes the self-healing "
             "purge surgical rather than total.")]

    gate_rows = [
        ["Accuracy must not regress", H.num(gates["min_accuracy_gain"], 3)],
        ["Poison resistance floor", H.num(gates["min_poison_resistance"], 2)],
        ["False-positive ceiling", H.num(gates["max_false_positive_rate"], 2)],
        ["Minimum pool size", H.esc(gates["min_samples"])],
    ]
    outcome = VIEW.last.get("11/retrain", {}).get("outcome") or {}
    if outcome:
        out.append(_retrain_card(outcome))
    else:
        out.append(H.card("The four promotion gates",
                          H.table(["Gate", ("Limit", "num")], gate_rows),
                          hint="A candidate that fails any one of these is "
                               "discarded with the incumbent left running. "
                               "The poison-resistance gate earns its place: a "
                               "backdoored model scores beautifully on "
                               "accuracy, because that is the whole point of "
                               "a backdoor."))

    lineage = state["registry"]["lineage"]
    if lineage:
        rows = [[H.esc(f"v{v['version']}"), H.pct(v["accuracy"]),
                 H.pct(v["macro_f1"]), H.num(v["poison_resistance"], 3),
                 H.badge("trusted", "ok") if v["trusted"]
                 else H.badge("distrusted", "bad"),
                 H.badge("active", "accent")
                 if v["version"] == state["registry"]["active"] else "",
                 f"<small>{H.esc(v['notes'])}</small>"]
                for v in lineage[::-1]]
        out.append(H.card("Model registry", H.table(
            ["Version", ("Accuracy", "num"), ("Macro F1", "num"),
             ("Poison resistance", "num"), "Trust", "", "Notes"], rows)))
    return "".join(out)


def _retrain_card(o: Dict[str, Any]) -> str:
    promoted = o["promoted"]
    gate_rows = []
    for name, g in (o.get("gates") or {}).items():
        limit = g.get("required", g.get("limit", g.get("required_gain")))
        gate_rows.append([
            H.esc(H.human(name)),
            H.num(g.get("value"), 4),
            H.num(limit, 4),
            H.badge("pass", "ok") if g["pass"] else H.badge("fail", "bad"),
        ])

    m = o.get("metrics") or {}
    inc = o.get("incumbent_metrics") or {}
    body = H.metrics([
        ("Outcome", "Promoted" if promoted else "Rejected", "",
         "ok" if promoted else "warn"),
        ("Accuracy", H.pct(m.get("accuracy")),
         f"incumbent {H.pct(inc.get('accuracy'))}" if inc else ""),
        ("False negatives", H.pct(m.get("false_negative_rate"))),
        ("Poison resistance",
         H.num((o.get("resistance") or {}).get("poison_resistance"), 4)),
        ("Training rows", (o.get("pool") or {}).get("training_rows")),
        ("Vaccine rows", (o.get("pool") or {}).get("vaccine_rows")),
        ("Took", f"{o.get('elapsed_s')}s"),
    ])
    body += H.note(o.get("reason", ""))
    body += H.table(["Gate", ("Value", "num"), ("Limit", "num"), "Result"],
                    gate_rows)
    res = (o.get("resistance") or {}).get("per_strategy") or {}
    if res:
        body += ("<h4>Poison resistance by rehearsed strategy</h4>"
                 + H.table(["Strategy", ("Surviving recall", "num"), ""],
                           [[H.esc(H.human(k)), H.num(v, 4),
                             H.bar(v, H.tone_for(v, 0.9, 0.78))]
                            for k, v in res.items()]))
    return H.card("Retraining outcome", body,
                  aside=H.badge("Promoted", "ok") if promoted
                  else H.badge("Rejected", "warn"))


# ===========================================================================
# STEP 12 -- self-healing
# ===========================================================================
def _step12(state: Dict[str, Any], extra: Dict[str, Any]) -> str:
    health = state["health"]
    thresholds = health["thresholds"]

    body = H.form("/step/12/check", "Run a health check")
    body += H.metrics([
        ("Observations seen", health["observations"]),
        ("Window", f"{health['window']}/{health['window_capacity']}"),
        ("Baseline agreement", H.num(health["baseline"], 4)
         if health["baseline"] is not None else "learning"),
        ("Baseline progress", health["baseline_progress"]),
        ("Checks run", health["checks_run"]),
        ("Heals", health["heals"]),
    ])
    check = (VIEW.last.get("12/check", {}).get("check")
             or state.get("last_check") or {})
    if check:
        if check.get("evaluated"):
            body += H.kv_list([
                ("Health score", H.num(check["health_score"], 4)),
                ("Model/twin agreement", H.num(check["agreement"], 4)),
                ("Baseline", H.num(check["baseline_agreement"], 4)),
                ("Drop vs baseline", H.pct(check["agreement_drop"], 1)),
                ("Detection rate", H.num(check["detection_rate"], 4)),
                ("False negative rate", H.pct(check["false_negative_rate"], 1)),
                ("Twin flags", check["twin_flags"]),
                ("Both flagged", check["both_flagged"]),
            ])
            body += (H.findings(check["reasons"]) if check["degraded"]
                     else H.note("No degradation signal. The twin and the "
                                 "model are agreeing as well as this model's "
                                 "own baseline says they should."))
        else:
            body += H.note(check.get("note", ""))
    out = [H.card(
        "Model health", body,
        hint="The twin and the classifier are independent detectors of the "
             "same events. When the twin keeps flagging deviations the model "
             "calls perfectly normal, a successfully poisoned classifier is "
             "the interesting explanation. The trigger is degradation against "
             "this model's own baseline, not an absolute rate.",
        aside=H.badge("Degraded", "bad") if check.get("degraded")
        else H.badge("Healthy", "ok") if check.get("evaluated")
        else H.badge("Not enough evidence", "pending"))]

    heal_body = H.form(
        "/step/12/heal", "Roll back and rebuild", kind="danger",
        body=H.controls(
            H.field("reason", "Reason for the record",
                    _fv(12, "reason", "operator-triggered"), kind="text"),
            H.select("retrain_after", "Retrain after healing",
                     [("no", "No -- inspect the cleaned pool first"),
                      ("yes", "Yes -- retrain immediately")],
                     _fv(12, "retrain_after", "no")),
            H.select("force", "If the model looks healthy",
                     [("no", "Refuse -- do not distrust a working model"),
                      ("yes", "Heal anyway, and record that I forced it")],
                     _fv(12, "force", "no"))))
    event = VIEW.last.get("12/heal", {}).get("event") or {}
    if event:
        heal_body += H.kv_list([
            ("Rolled back from", f"v{event.get('from_version')}"),
            ("Rolled back to",
             f"v{event['rolled_back_to']}" if event.get("rolled_back_to")
             else "no earlier trusted version"),
            ("Distrusted", ", ".join(f"v{v}" for v in event.get("distrusted", []))
             or "none"),
            ("Rows purged", event.get("purged_rows", 0)),
            ("Sources purged", ", ".join(event.get("purged_sources", []))
             or "none"),
            ("Pool after", event.get("pool_after")),
        ])
        if event.get("note"):
            heal_body += H.note(event["note"])
    out.append(H.card(
        "Heal: roll back, purge, rebuild", heal_body,
        hint="In that order, and never in place. You cannot subtract poison "
             "from a trained model -- you can only return to one you trust and "
             "regrow it from a cleaned pool. Sources with anything still held "
             "in quarantine lose every row they ever contributed. Healing a "
             "model the monitor calls healthy is refused unless you override "
             "it, because nothing can re-trust a model afterwards."))

    out.append(H.card("Thresholds", H.kv_list([
        ("Max agreement drop", thresholds["max_agreement_drop"]),
        ("Min detection rate", thresholds["min_detection_rate"]),
        ("Max false negative rate", thresholds["max_false_negative_rate"]),
        ("Min health score", thresholds["min_health_score"]),
        ("Twin flags needed to judge", thresholds["min_flags_for_verdict"]),
    ])))

    lineage = state["registry"]["lineage"]
    if lineage:
        rows = []
        for v in lineage[::-1]:
            active = v["version"] == state["registry"]["active"]
            rows.append([
                H.esc(f"v{v['version']}"),
                H.pct(v["accuracy"]),
                H.num(v["poison_resistance"], 3),
                H.badge("trusted", "ok") if v["trusted"]
                else H.badge("distrusted", "bad"),
                H.badge("active", "accent") if active else "",
                H.form("/step/12/rollback", f"Activate v{v['version']}",
                       fields={"version": v["version"]}, kind="ghost sm",
                       inline=True) if not active else "",
            ])
        out.append(H.card(
            "Roll back by hand",
            H.table(["Version", ("Accuracy", "num"),
                     ("Poison resistance", "num"), "Trust", "", ""], rows),
            hint="Nothing in the registry is ever overwritten, which is what "
                 "makes a rollback to a known-good version possible."))
    return "".join(out)


RENDERERS: Dict[int, Callable[[Dict[str, Any], Dict[str, Any]], str]] = {
    1: _step1, 2: _step2, 3: _step3, 4: _step4, 5: _step5, 6: _step6,
    7: _step7, 8: _step8, 9: _step9, 10: _step10, 11: _step11, 12: _step12,
}
