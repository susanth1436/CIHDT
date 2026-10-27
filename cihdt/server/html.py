"""HTML primitives for the server-rendered console.

The console is a multi-page application: one real URL per step, one full page
load per operator action, and no client-side JavaScript at all.  That is not
nostalgia, it follows from what this project is.  The system only ever moves
when the operator moves it, so there is never anything to push, poll or
reconcile -- and a POST that redirects to a GET means a browser refresh
re-reads the page instead of silently re-firing the action it just ran.

Everything here is a plain function returning an HTML fragment.  There is no
template engine and no build step: the whole UI is this module plus one small
stylesheet, so a reviewer can read the page source and the code that produced
it side by side.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------
def esc(value: Any) -> str:
    """Escape a value for use as HTML text or inside a quoted attribute."""
    if value is None:
        return ""
    return "".join(_ESCAPES.get(ch, ch) for ch in str(value))


def num(value: Any, digits: int = 2) -> str:
    try:
        if value is None:
            return "--"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "--"


def pct(value: Any, digits: int = 1) -> str:
    try:
        if value is None:
            return "--"
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "--"


# Names that str.title() gets wrong, and that an operator would notice.
_ACRONYMS = {"Ddos": "DDoS", "C2": "C2", "Cpu": "CPU", "Ips": "IPs",
             "Ccs": "CCS", "Fpr": "FPR", "Fnr": "FNR"}


def human(value: Any) -> str:
    """``botnet_c2`` -> ``Botnet C2``, ``ddos`` -> ``DDoS``."""
    words = str(value or "").replace("_", " ").title().split()
    return " ".join(_ACRONYMS.get(w, w) for w in words)


def plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many or one + 's'}"


# ---------------------------------------------------------------------------
# blocks
# ---------------------------------------------------------------------------
def slug(text: Any) -> str:
    """A stable id for a heading, so a card can be linked to."""
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(text or ""))
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "section"


def card(heading: str, body: str, hint: str = "", aside: str = "",
         anchor: str = "") -> str:
    """One panel.

    Every card carries an id derived from its heading, because each operator
    action is a full page load: without somewhere to land, the browser would
    drop the operator back at the top of the page after every click. The POST
    redirects to the id of the card whose button was pressed, so the page comes
    back where it was left. ``anchor`` overrides the derived id for headings
    that carry a record id and therefore change between renders.
    """
    head = f"<h2>{esc(heading)}</h2>"
    if hint:
        head += f"<p class='hint'>{esc(hint)}</p>"
    aside_html = f"<div class='card-aside'>{aside}</div>" if aside else ""
    return (f"<section class='card' id='{esc(anchor or slug(heading))}'>"
            f"<header>{head}{aside_html}</header>{body}</section>")


def table(columns: Sequence[Any], rows: Sequence[Sequence[str]]) -> str:
    """A table.  ``columns`` entries are a label, or a ``(label, 'num')`` pair.

    Row cells are inserted verbatim so a caller can pass a badge or a nested
    form; every such cell is built by a helper in this module, each of which
    escapes its own inputs.
    """
    if not rows:
        return ""
    head: List[str] = []
    aligns: List[str] = []
    for col in columns:
        label, align = col if isinstance(col, tuple) else (col, "")
        aligns.append(align)
        cls = " class='num'" if align == "num" else ""
        head.append(f"<th{cls}>{esc(label)}</th>")

    body: List[str] = []
    for r in rows:
        cells = []
        for i, cell in enumerate(r):
            cls = " class='num'" if i < len(aligns) and aligns[i] == "num" else ""
            cells.append(f"<td{cls}>{cell}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")

    return ("<div class='scroll'><table><thead><tr>" + "".join(head)
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def metrics(items: Iterable[Tuple[Any, ...]]) -> str:
    """A row of readings.  Items are ``(label, value[, note[, tone]])``."""
    out = []
    for item in items:
        label, value = item[0], item[1]
        sub = item[2] if len(item) > 2 else ""
        tone = item[3] if len(item) > 3 else ""
        cls = f"metric {tone}".strip()
        note_html = f"<span class='m-note'>{esc(sub)}</span>" if sub else ""
        out.append(f"<div class='{esc(cls)}'><span class='m-label'>{esc(label)}"
                   f"</span><span class='m-value'>{esc(value)}</span>"
                   f"{note_html}</div>")
    return f"<div class='metrics'>{''.join(out)}</div>" if out else ""


def badge(text: Any, kind: str = "") -> str:
    return f"<span class='badge {esc(kind)}'>{esc(text)}</span>"


def bar(fraction: Any, kind: str = "") -> str:
    try:
        width = max(0.0, min(1.0, float(fraction))) * 100.0
    except (TypeError, ValueError):
        width = 0.0
    return (f"<span class='bar {esc(kind)}'>"
            f"<i style='width:{width:.1f}%'></i></span>")


def tone_for(value: Any, good: float = 0.85, ok: float = 0.6) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    return "ok" if v >= good else "warn" if v >= ok else "bad"


def empty(text: str) -> str:
    return f"<p class='empty'>{esc(text)}</p>"


def note(text: str) -> str:
    return f"<p class='note'>{esc(text)}</p>"


def tags(values: Iterable[Any]) -> str:
    inner = "".join(f"<span class='tag'>{esc(human(v))}</span>" for v in values)
    return f"<div class='tags'>{inner}</div>" if inner else ""


def kv_list(pairs: Iterable[Tuple[Any, Any]]) -> str:
    rows = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>"
                   for k, v in pairs)
    return f"<dl class='kv'>{rows}</dl>" if rows else ""


def findings(items: Iterable[Any]) -> str:
    inner = "".join(f"<li>{esc(f)}</li>" for f in items)
    return f"<ul class='findings'>{inner}</ul>" if inner else ""


# ---------------------------------------------------------------------------
# forms
# ---------------------------------------------------------------------------
def field(name: str, label: str, value: Any = "", kind: str = "number",
          **attrs: Any) -> str:
    extra = "".join(f" {k.replace('_', '-')}='{esc(v)}'"
                    for k, v in attrs.items() if v is not None)
    return (f"<label class='field'><span>{esc(label)}</span>"
            f"<input type='{esc(kind)}' name='{esc(name)}' "
            f"value='{esc(value)}'{extra}></label>")


def select(name: str, label: str, options: Sequence[Tuple[Any, Any]],
           value: Any = None) -> str:
    opts = "".join(
        f"<option value='{esc(v)}'{' selected' if str(v) == str(value) else ''}>"
        f"{esc(text)}</option>" for v, text in options)
    return (f"<label class='field'><span>{esc(label)}</span>"
            f"<select name='{esc(name)}'>{opts}</select></label>")


def radio_cards(name: str, options: Sequence[Tuple[Any, str, str]],
                value: Any = None) -> str:
    """Radio buttons rendered as selectable cards: ``(value, label, detail)``."""
    out = []
    for val, label, detail in options:
        checked = " checked" if str(val) == str(value) else ""
        out.append(
            f"<label class='choice'><input type='radio' name='{esc(name)}' "
            f"value='{esc(val)}'{checked}>"
            f"<span class='choice-body'><b>{esc(label)}</b>"
            f"<span>{esc(detail)}</span></span></label>")
    return f"<div class='choices'>{''.join(out)}</div>"


def checkboxes(name: str, options: Sequence[Tuple[Any, str]],
               checked: Sequence[Any] = ()) -> str:
    marks = {str(c) for c in checked}
    out = []
    for val, label in options:
        on = " checked" if str(val) in marks else ""
        out.append(f"<label class='check'><input type='checkbox' "
                   f"name='{esc(name)}' value='{esc(val)}'{on}>"
                   f"<span>{esc(label)}</span></label>")
    return f"<div class='checks'>{''.join(out)}</div>"


def hidden(values: Optional[Dict[str, Any]]) -> str:
    if not values:
        return ""
    return "".join(f"<input type='hidden' name='{esc(k)}' value='{esc(v)}'>"
                   for k, v in values.items())


def form(action: str, submit: str, body: str = "",
         fields: Optional[Dict[str, Any]] = None, kind: str = "",
         disabled: bool = False, inline: bool = False, hint: str = "",
         because: str = "") -> str:
    """One operator action: a POST that redirects back to a GET.

    ``because`` is the reason a control is greyed out, and it is shown beside
    it.  A disabled button with no explanation is indistinguishable from a
    broken one, which is exactly how an operator concludes the console does
    not work.
    """
    cls = "act" + (" inline" if inline else "")
    btn_cls = f"btn {kind}".strip()
    off = " disabled" if disabled else ""
    hint_html = f"<p class='hint'>{esc(hint)}</p>" if hint else ""
    why = (f"<span class='why'>{esc(because)}</span>"
           if disabled and because else "")
    return (f"<form class='{cls}' method='post' action='{esc(action)}'>"
            f"{hidden(fields)}{hint_html}{body}"
            f"<button class='{esc(btn_cls)}' type='submit'{off}>"
            f"{esc(submit)}</button>{why}</form>")


def controls(*parts: str) -> str:
    """Lay several fields and a submit button out on one line."""
    return f"<div class='controls'>{''.join(p for p in parts if p)}</div>"


def row(*parts: str) -> str:
    return f"<div class='row'>{''.join(p for p in parts if p)}</div>"


# ---------------------------------------------------------------------------
# the post-run explanation card
# ---------------------------------------------------------------------------
_TONES = {"good": "good", "warn": "warn", "bad": "bad", "info": "info"}


def explanation(card_data: Optional[Dict[str, Any]]) -> str:
    """Render the server-generated "what just happened" card.

    The text comes from :mod:`cihdt.explain`, so this page and the terminal
    front end tell the operator the same story from one source.
    """
    if not card_data:
        return ""
    tone = _TONES.get(card_data.get("tone", "info"), "info")

    bullets = "".join(f"<li>{esc(b)}</li>"
                      for b in card_data.get("what_happened", []))
    bullets = f"<ul class='happened'>{bullets}</ul>" if bullets else ""

    readings = []
    for r in card_data.get("reading", []):
        verdict = r.get("verdict")
        chip = (f"<span class='chip {esc(str(verdict).replace(' ', '-'))}'>"
                f"{esc(verdict)}</span>" if verdict else "")
        readings.append(
            f"<div class='reading'><span class='r-label'>{esc(r.get('label'))}"
            f"</span><span class='r-value'>{esc(r.get('value'))}{chip}</span>"
            f"<span class='r-note'>{esc(r.get('note'))}</span></div>")
    readings_html = (f"<div class='readings'>{''.join(readings)}</div>"
                     if readings else "")

    matters = card_data.get("why_it_matters")
    matters_html = (f"<div class='block'><h4>Why it matters</h4>"
                    f"<p>{esc(matters)}</p></div>" if matters else "")

    nxt = card_data.get("next")
    step = card_data.get("next_step")
    link = (f"<a class='btn next' href='/step/{int(step)}'>"
            f"Go to Step {int(step)} &rarr;</a>" if step else "")
    next_html = (f"<div class='block next-block'><h4>Next</h4><p>{esc(nxt)}</p>"
                 f"{link}</div>" if nxt else "")

    return (f"<section class='explain {tone}'>"
            f"<p class='eyebrow'>What just happened</p>"
            f"<h3>{esc(card_data.get('headline'))}</h3>"
            f"{bullets}{readings_html}{matters_html}{next_html}</section>")


# ---------------------------------------------------------------------------
# the page shell -- a website, not a dashboard
#
# Every page is one step and nothing else: a full-bleed hero naming it, the
# controls for that step, and a band at the foot that carries the operator to
# the next one.  There is no rail listing all twelve, because a page showing
# you eleven other things is a control panel, and this is meant to read like a
# site you move through.
# ---------------------------------------------------------------------------
N_STEPS = 12


def two_tone(title: str) -> Tuple[str, str]:
    """Split a heading into a heavy first word and a light remainder.

    ``Generate counterfactual futures`` becomes GENERATE / COUNTERFACTUAL
    FUTURES -- the two-weight headline the whole design is built around.
    """
    words = str(title or "").split()
    if not words:
        return "", ""
    return words[0].upper(), " ".join(words[1:]).upper()


def topnav(current: Optional[int] = None,
           user: Optional[Dict[str, Any]] = None) -> str:
    brand = (f"<a class='logo' href='/'>"
             f"<span class='mark' aria-hidden='true'></span>"
             f"<span class='word'><b>CIHDT</b> CONSOLE</span></a>")
    if user is None:
        # Signed out: nothing to navigate to but the way in.
        return f"<header class='nav'>{brand}<nav></nav></header>"

    links = [("/", "Home", current is None),
             ("/start", "Telemetry Source", False),
             ("/step/1", "The Twelve Steps", current is not None),
             ("/accounts", "Accounts", False),
             ("/activity", "Activity", False),
             ("/results", "Results", False),
             ("/docs", "API", False)]
    items = "".join(
        f"<a href='{esc(href)}'{' class=on' if on else ''}>{esc(label)}</a>"
        for href, label, on in links)
    who = (f"<span class='who' title='Signed in'>"
           f"{esc(user.get('display_name') or user.get('username'))}</span>")
    out = (f"<form class='act inline' method='post' action='/logout'>"
           f"<button class='btn ghost sm' type='submit'>Sign out</button>"
           f"</form>")
    return (f"<header class='nav'>{brand}"
            f"<nav>{items}<a class='reset' href='/reset'>Reset</a>"
            f"{who}{out}</nav></header>")


def hero(eyebrow: str, title: str, lede: str = "", cta: str = "",
         compact: bool = False) -> str:
    bold, light = two_tone(title)
    light_html = f"<span>{esc(light)}</span>" if light else ""
    return (f"<section class='hero{' compact' if compact else ''}'>"
            f"<div class='wrap'>"
            f"<p class='eyebrow'>{esc(eyebrow)}</p>"
            f"<h1><b>{esc(bold)}</b>{light_html}</h1>"
            + (f"<p class='lede'>{esc(lede)}</p>" if lede else "")
            + (f"<div class='hero-cta'>{cta}</div>" if cta else "")
            + "</div></section>")


def stat_strip(state: Dict[str, Any]) -> str:
    """A thin line of live figures, so a page stands on its own."""
    model = state.get("model") or {}
    chips = [
        ("Devices", state["fleet"]["n_devices"]),
        ("Ticks", state["stats"]["ticks"]),
        ("Twins ready", f"{state['twins']['ready']}/{state['twins']['count']}"),
        ("Model", f"v{model['version']}" if model else "none"),
        ("Bank", state["bank"]["n"]),
        ("Safe pool", state["retrainer"]["pool_size"]),
        ("Held", state["quarantine"]["held"]),
    ]
    out = "".join(f"<span><b>{esc(v)}</b>{esc(k)}</span>" for k, v in chips)
    return f"<div class='stats'><div class='wrap'>{out}</div></div>"


def progress_rail(state: Dict[str, Any], current: int) -> str:
    """How far through the twelve the operator is."""
    done = sum(1 for s in state["steps"] if s["status"] == "done")
    width = done / N_STEPS * 100.0
    return (f"<div class='progress'><div class='wrap'>"
            f"<span class='p-label'>Step {current} of {N_STEPS}</span>"
            f"<span class='p-track'><i style='width:{width:.1f}%'></i></span>"
            f"<span class='p-count'>{done} of {N_STEPS} complete</span>"
            f"</div></div>")


def continue_band(state: Dict[str, Any], current: int) -> str:
    """The foot of a step page: where the operator goes once this is finished."""
    steps = {s["id"]: s for s in state["steps"]}
    spec = steps[current]
    done = spec["status"] == "done"
    back = (f"<a class='back' href='/step/{current - 1}'>&larr; Back to Step "
            f"{current - 1}</a>" if current > 1
            else "<a class='back' href='/'>&larr; Back to the overview</a>")
    foot = f"<div class='band-foot'><div class='wrap'>{back}</div></div>"

    if spec["status"] == "locked":
        return foot

    if current == N_STEPS:
        if done:
            inner = ("<p class='eyebrow'>The walkthrough is complete</p>"
                     "<h2><b>WHAT THIS</b><span>RUN PROVED</span></h2>"
                     "<p>Every stage has been run by hand, in order. The "
                     "evidence is spread over six pages; this gathers it into "
                     "one verdict.</p>"
                     "<a class='btn big' href='/results'>"
                     "See the conclusion &rarr;</a>")
        else:
            inner = ("<p class='eyebrow'>Final step</p>"
                     "<h2><b>TWELVE</b><span>OF TWELVE</span></h2>"
                     "<p>Finish this step to complete the walkthrough.</p>"
                     "<a class='btn big' href='/'>Back to the overview</a>")
        return (f"<section class='band continue'><div class='wrap narrow'>"
                f"{inner}</div></section>{foot}")

    nxt = steps[current + 1]
    if done:
        bold, light = two_tone(nxt["title"])
        inner = (f"<p class='eyebrow'>Step {current} complete</p>"
                 f"<h2><b>{esc(bold)}</b><span>{esc(light)}</span></h2>"
                 f"<p>{esc(nxt['purpose'])}</p>"
                 f"<a class='btn big' href='/step/{current + 1}'>"
                 f"Continue to Step {current + 1} &rarr;</a>")
        cls = "band continue"
    else:
        inner = (f"<p class='eyebrow'>Step {current} is not finished yet</p>"
                 f"<h2><b>STEP {current + 1}</b><span>IS LOCKED</span></h2>"
                 f"<p>{esc(nxt['title'])} unlocks once this step is complete. "
                 f"Run the actions above to finish it.</p>"
                 f"<span class='btn big off'>Continue to Step "
                 f"{current + 1} &rarr;</span>")
        cls = "band continue pending"
    return (f"<section class='{cls}'><div class='wrap narrow'>{inner}</div>"
            f"</section>{foot}")


def flash(message: Optional[Dict[str, Any]]) -> str:
    if not message:
        return ""
    step = message.get("required_step")
    link = (f" <a href='/step/{int(step)}'>Go to Step {int(step)}</a>"
            if step else "")
    return (f"<div class='flash' role='alert'><b>Cannot do that yet.</b> "
            f"{esc(message.get('message'))}{link}</div>")


def split(bold: str, light: str, body: str, blurb: str = "") -> str:
    """The template's signature block: pale heading panel, white content."""
    return (f"<section class='split'><div class='wrap'>"
            f"<aside><h2><b>{esc(bold)}</b><span>{esc(light)}</span></h2>"
            + (f"<p>{esc(blurb)}</p>" if blurb else "")
            + f"</aside><div class='split-body'>{body}</div>"
            f"</div></section>")


def feature_grid(items: Sequence[Tuple[str, str, str]]) -> str:
    """Teal-square items in two columns: ``(href, title, body)``."""
    out = []
    for href, title, body in items:
        head = (f"<a href='{esc(href)}'>{esc(title)}</a>" if href
                else f"<span>{esc(title)}</span>")
        out.append(f"<article class='feat'><h3>{head}</h3>"
                   f"<p>{esc(body)}</p></article>")
    return f"<div class='feats'>{''.join(out)}</div>"


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
_ICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' "
         "viewBox='0 0 32 32'><rect width='32' height='32' fill='%230d3362'/>"
         "<path d='M7 7h8v8l10 10h-8V17L7 7z' fill='%2345c0bb'/></svg>")


def _document(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} &middot; CIHDT</title>
<link rel="stylesheet" href="/static/styles.css">
<link rel="icon" href="{_ICON}">
</head>
<body>
{body}
<footer class="foot"><div class="wrap">
  <p><b>CIHDT</b> &mdash; Counterfactual Immunization of Holographic Digital
     Twins. Predictive edge AI retraining for real-time threat detection in
     consumer IoT networks.</p>
  <p class="fine">Nothing here runs on its own. Every control is one operator
     action, and each action is a POST that redirects back to a page &mdash; so
     a refresh re-reads the result instead of repeating the action.</p>
</div></footer>
</body>
</html>"""


def page(*, title_text: str, state: Dict[str, Any], current: int, body: str,
         eyebrow: str = "", lede: str = "",
         message: Optional[Dict[str, Any]] = None,
         show_continue: bool = True,
         user: Optional[Dict[str, Any]] = None) -> str:
    """One step, as a page."""
    inner = (topnav(current, user)
             + hero(eyebrow, title_text, lede)
             + stat_strip(state)
             + progress_rail(state, current)
             + f"<main class='wrap main'>{flash(message)}{body}</main>"
             + (continue_band(state, current) if show_continue else ""))
    return _document(title_text, inner)


def plain_page(*, title_text: str, body: str, eyebrow: str = "",
               lede: str = "", message: Optional[Dict[str, Any]] = None,
               user: Optional[Dict[str, Any]] = None) -> str:
    """A page that is not one of the twelve, such as the reset confirmation."""
    inner = (topnav(None, user) + hero(eyebrow, title_text, lede, compact=True)
             + f"<main class='wrap main'>{flash(message)}{body}</main>")
    return _document(title_text, inner)


def landing(state: Dict[str, Any],
            message: Optional[Dict[str, Any]] = None,
            user: Optional[Dict[str, Any]] = None) -> str:
    """The front door: what this is, and the twelve steps laid out."""
    done = sum(1 for s in state["steps"] if s["status"] == "done")
    resume = next((s["id"] for s in state["steps"]
                   if s["status"] != "done"), N_STEPS)
    if state.get("source_mode") is None:
        # The source has to be chosen before any device can be deployed.
        cta = "<a class='btn big' href='/start'>Begin &mdash; choose a source &rarr;</a>"
    else:
        label = (f"Continue at Step {resume}" if done else "Begin at Step 1")
        cta = f"<a class='btn big' href='/step/{resume}'>{esc(label)} &rarr;</a>"
        if done == N_STEPS:
            cta = ("<a class='btn big' href='/results'>"
                   "See what this run proved &rarr;</a>")

    marks = {"done": "Complete", "ready": "Ready", "locked": "Locked"}
    items = [("" if s["status"] == "locked" else f"/step/{s['id']}",
              f"{s['id']:02d}. {s['title']}",
              f"{s['subtitle']}. {marks[s['status']]}.")
             for s in state["steps"]]

    mechanism = (
        "<section class='band'><div class='wrap narrow'>"
        "<h2 class='centred'><b>OUR</b><span>MECHANISM</span></h2>"
        "<p>A conventional federated defence asks whether a contribution looks "
        "like the others. That is a question about the past, and an attacker "
        "answers it by staying close to the crowd.</p>"
        "<p>This one asks a different question: <em>if I accepted this update, "
        "what would it do to my ability to catch tomorrow's attack?</em> The "
        "update is grafted onto a trusted core, a shadow model is trained, and "
        "that shadow is put in front of futures the twins committed to before "
        "the update existed.</p>"
        "<p>Simulated poisoning scenarios then retrain and immunize the edge "
        "model before real poisoning ever reaches the network.</p>"
        "</div></section>")

    inner = (topnav(None, user)
             + hero("Counterfactual immunization of holographic digital twins",
                    "Predictive edge AI",
                    "A twelve-step operator console for real-time threat "
                    "detection in consumer IoT networks — driven by a "
                    "simulated fleet, or by the real USB devices attached to "
                    "this machine. You choose. You run every step. Nothing "
                    "happens on its own.",
                    cta=cta)
             + stat_strip(state)
             + f"<main class='wrap main'>{flash(message)}</main>"
             + split("THE TWELVE", "STEPS", feature_grid(items),
                     "Each step is its own page. Finish one and it carries you "
                     "to the next; a step you have not earned yet stays "
                     "locked.")
             + mechanism)
    return _document("Home", inner)


# ---------------------------------------------------------------------------
# the way in
# ---------------------------------------------------------------------------
def auth_page(*, error: str = "", notice: str = "",
              next_url: str = "/", email: str = "") -> str:
    """The sign-in page.

    The error text is deliberately the same whether the account does not exist
    or the password was wrong.  Telling the two apart hands an attacker a list
    of real addresses for free.
    """
    error_html = (f"<div class='flash' role='alert'><b>Sign-in failed.</b> "
                  f"{esc(error)}</div>" if error else "")
    notice_html = (f"<p class='signin-notice'>{esc(notice)}</p>"
                   if notice else "")

    form = (
        f"<form class='signin' method='post' action='/login'>"
        f"{hidden({'next': next_url})}"
        f"<label class='field'><span>Email address</span>"
        f"<input type='email' name='email' value='{esc(email)}' "
        f"autocomplete='username' autocapitalize='none' autocorrect='off' "
        f"spellcheck='false' placeholder='you@example.com' required autofocus>"
        f"</label>"
        f"<label class='field'><span>Password</span>"
        f"<input type='password' name='password' "
        f"autocomplete='current-password' required></label>"
        f"<button class='btn big' type='submit'>Sign in</button>"
        f"</form>"
        f"<p class='signin-alt'>No account yet? "
        f"<a href='/register'>Create one</a>.</p>")

    inner = (
        topnav(None, None)
        + "<section class='hero compact signin-hero'><div class='wrap'>"
          "<p class='eyebrow'>Counterfactual immunization of holographic "
          "digital twins</p>"
          "<h1><b>SIGN IN</b><span>TO THE CONSOLE</span></h1>"
          "<p class='lede'>This console trains models, accepts training "
          "contributions and can roll a deployed model back. It is not open "
          "to the network.</p>"
          "</div></section>"
        + f"<main class='wrap main signin-main'>{error_html}"
          f"<section class='card signin-card'>"
          f"<header><h2>Operator sign-in</h2></header>"
          f"{form}{notice_html}</section></main>")
    return _document("Sign in", inner)


def register_page(*, error: str = "", email: str = "", display_name: str = "",
                  needs_code: bool = True) -> str:
    """The create-account page."""
    error_html = (f"<div class='flash' role='alert'><b>Could not create the "
                  f"account.</b> {esc(error)}</div>" if error else "")

    code_field = (
        "<label class='field'><span>Registration code</span>"
        "<input type='text' name='code' autocomplete='off' "
        "autocapitalize='none' spellcheck='false' required></label>"
        if needs_code else "")
    code_note = (
        "<p class='signin-notice'>A registration code is required on this "
        "instance. Ask whoever runs the console for the current one &mdash; it "
        "is printed in the terminal that started the server, and shown on the "
        "Accounts page to anyone already signed in.</p>"
        if needs_code else
        "<p class='signin-notice'>Your password is stored only as a salted "
        "PBKDF2 derivation, never in the clear, and every action you take in "
        "the console is recorded against this address.</p>")

    form = (
        f"<form class='signin' method='post' action='/register'>"
        f"<label class='field'><span>Email address</span>"
        f"<input type='email' name='email' value='{esc(email)}' "
        f"autocomplete='username' autocapitalize='none' autocorrect='off' "
        f"spellcheck='false' placeholder='you@example.com' required autofocus>"
        f"</label>"
        f"<label class='field'><span>Your name</span>"
        f"<input type='text' name='display_name' "
        f"value='{esc(display_name)}' autocomplete='name' maxlength='48'>"
        f"</label>"
        f"<label class='field'><span>Password</span>"
        f"<input type='password' name='password' minlength='8' "
        f"autocomplete='new-password' required></label>"
        f"<label class='field'><span>Confirm password</span>"
        f"<input type='password' name='confirm' minlength='8' "
        f"autocomplete='new-password' required></label>"
        f"{code_field}"
        f"<button class='btn big' type='submit'>Create account</button>"
        f"</form>"
        f"<p class='signin-alt'>Already have an account? "
        f"<a href='/login'>Sign in</a>.</p>")

    inner = (
        topnav(None, None)
        + "<section class='hero compact signin-hero'><div class='wrap'>"
          "<p class='eyebrow'>Counterfactual immunization of holographic "
          "digital twins</p>"
          "<h1><b>CREATE</b><span>AN ACCOUNT</span></h1>"
          "<p class='lede'>Everyone who operates this console signs in under "
          "their own address, so every action can be attributed to the person "
          "who took it.</p>"
          "</div></section>"
        + f"<main class='wrap main signin-main'>{error_html}"
          f"<section class='card signin-card'>"
          f"<header><h2>New operator</h2></header>"
          f"{form}{code_note}</section></main>")
    return _document("Create an account", inner)
