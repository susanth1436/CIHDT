"""Post-run explanations: what just happened, and what the numbers mean.

Every step panel already says what it is *about* to do.  This module produces
the other half -- an explanation generated *after* the step runs, from the
numbers that step actually produced.

The rule this module follows, and the reason it is worth having at all: every
sentence must be derived from the result, never boilerplate.  It does not say
"the detector was trained successfully"; it says which of the two error rates
came out worse and what that specific value would mean on a real network.  A
generic explanation teaches nobody anything they could not have guessed, and
the interesting cases are precisely the ones where the numbers came out badly.

It lives on the server rather than in the browser so the console and the
terminal front end tell the operator exactly the same story.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .config import SETTINGS
from .poisoning.attacks import STRATEGY_TEXT

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _pct(v: Optional[float], digits: int = 1) -> str:
    return "--" if v is None else f"{float(v) * 100:.{digits}f}%"


def _num(v: Optional[float], digits: int = 3) -> str:
    return "--" if v is None else f"{float(v):.{digits}f}"


def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one}" if n == 1 else f"{n} {many or one + 's'}"


def _card(headline: str, happened: List[str], reading: List[Dict[str, Any]],
          matters: str, nxt: str, next_step: Optional[int] = None,
          tone: str = "info") -> Dict[str, Any]:
    """One explanation card.

    ``tone`` drives the colour in the console: info, good, warn, bad.
    """
    return {"headline": headline, "what_happened": happened,
            "reading": reading, "why_it_matters": matters,
            "next": nxt, "next_step": next_step, "tone": tone}


def _r(label: str, value: Any, note: str, verdict: str = "") -> Dict[str, Any]:
    return {"label": label, "value": str(value), "note": note,
            "verdict": verdict}


# ---------------------------------------------------------------------------
# STEP 1 -- devices
# ---------------------------------------------------------------------------
def _add_device(res: Dict[str, Any], p) -> Dict[str, Any]:
    fleet = res.get("fleet", {})
    layout = fleet.get("layout", {})
    n = fleet.get("n_devices", 0)
    mix = ", ".join(f"{k.replace('_', ' ')} x{v}" for k, v in layout.items())

    if n < 2:
        nxt = "Add at least one more device -- the gateway needs two to start."
        tone, step = "warn", 1
    else:
        nxt = "Move to Step 2 and start the edge gateway."
        tone, step = "good", 2

    return _card(
        headline=f"Network now has {_plural(n, 'device')}.",
        happened=[
            f"Added {res.get('device', {}).get('device_id', 'a device')} to the "
            f"simulated home network.",
            f"Current mix: {mix or 'nothing yet'}.",
            "No telemetry has been produced yet. The device sits idle until "
            "you collect a tick in Step 2.",
        ],
        reading=[
            _r("Devices", n, "each one gets its own twin and its own baseline"),
            _r("Distinct types", len(layout),
               "more types means a harder, more realistic detection problem"),
        ],
        matters=(
            "This choice propagates through everything downstream. The labelled "
            "corpus in Step 6 is generated from these exact device profiles, so "
            "the model is trained on the network it will actually police. A "
            "fleet of bulbs and sensors produces a very different notion of "
            "normal from one with three cameras in it."),
        nxt=nxt, next_step=step, tone=tone)


# ---------------------------------------------------------------------------
# STEP 2 -- gateway
# ---------------------------------------------------------------------------
def _start_gateway(res: Dict[str, Any], p) -> Dict[str, Any]:
    g = res.get("gateway", {})
    return _card(
        headline="Edge gateway is online.",
        happened=[
            f"The gateway is now accepting telemetry from "
            f"{_plural(g.get('devices', 0), 'device')}.",
            "Everything from here -- twins, detection, validation, retraining -- "
            "runs locally. Nothing is sent to a cloud.",
            "No data has been collected yet.",
        ],
        reading=[_r("Devices attached", g.get("devices", 0),
                    "all processing stays on this machine")],
        matters=(
            "Keeping the gateway local is not only a latency argument. A "
            "consumer network that depends on a vendor cloud for its security "
            "inherits that vendor's compromise, and the update channel from "
            "that cloud is the single most attractive poisoning vector in the "
            "whole system. Validating and retraining on the gateway means the "
            "defence survives the update channel turning hostile."),
        nxt="Collect telemetry below. 45 ticks is enough to warm the twins.",
        next_step=2, tone="good")


def _collect(res: Dict[str, Any], p) -> Dict[str, Any]:
    ticks = res.get("ticks_collected", 0)
    obs = res.get("observations", 0)
    buffered = res.get("buffered_batches", 0)
    min_fit = SETTINGS.twin.min_fit
    enough = ticks >= min_fit

    return _card(
        headline=f"Collected {_plural(ticks, 'tick')} -- "
                 f"{obs} observations buffered.",
        happened=[
            f"Each tick produced one observation from every device, so "
            f"{ticks} ticks x {len(p.fleet)} devices = {obs} rows.",
            f"{buffered} batch(es) are held at the gateway. They have not "
            f"reached the twins yet -- that is a separate, deliberate step.",
            "Every value was clamped to a physically valid range, and counts "
            "like failed logins were rounded to integers.",
        ],
        reading=[
            _r("Ticks", ticks,
               f"a twin needs {min_fit} observations before it will fit",
               "enough" if enough else "not yet enough"),
            _r("Observations", obs, "these are the rows the twins will learn from"),
            _r("Buffered", buffered, "waiting for Step 3 to fold them in"),
        ],
        matters=(
            "The buffer exists so that collection and learning are separate "
            "actions. In an automatic system telemetry flows straight into the "
            "model of normal, which is exactly the door a slow poisoning attack "
            "walks through. Here you decide what gets learned."),
        nxt=("Go to Step 3, create the twins, then feed them this buffer."
             if enough else
             f"Collect more -- {min_fit} ticks are needed before a twin can fit "
             f"its predictor."),
        next_step=3 if enough else 2,
        tone="good" if enough else "warn")


# ---------------------------------------------------------------------------
# STEP 3 -- twins
# ---------------------------------------------------------------------------
def _create_twins(res: Dict[str, Any], p) -> Dict[str, Any]:
    created = res.get("created", [])
    return _card(
        headline=f"Created {_plural(len(created), 'holographic twin')}.",
        happened=[
            "Each twin is empty: it has no history and no idea what its device "
            "considers normal.",
            "A twin holds five separate projections of its device -- resource, "
            "network, access, topology, actuation -- rather than one combined "
            "state vector.",
        ],
        reading=[_r("Twins", len(p.twins), "one per physical device"),
                 _r("With history", p.twins.ready_count,
                    "none until you feed them")],
        matters=(
            "The five planes are what makes this holographic rather than just a "
            "digital twin. Attacks are not uniform: a port scan detonates the "
            "topology plane and barely touches resources, while tampered "
            "firmware does the opposite. Scoring each plane separately stops a "
            "single loud plane being averaged into invisibility by four quiet "
            "ones."),
        nxt="Feed the buffered telemetry into the twins.",
        next_step=3, tone="info")


def _feed_twins(res: Dict[str, Any], p) -> Dict[str, Any]:
    fed = res.get("observations_fed", 0)
    ready = res.get("ready", 0)
    total = len(p.twins)
    min_fit = res.get("min_fit", SETTINGS.twin.min_fit)
    all_ready = ready == total and total > 0

    return _card(
        headline=(f"{ready} of {total} twins now have enough history."
                  if not all_ready else
                  f"All {total} twins are ready."),
        happened=[
            f"Folded {fed} observations into the twins.",
            "Each twin updated a smoothed mean and variance per feature, which "
            "becomes its personal yardstick for how far is far.",
            "These observations were trusted without question -- this is the "
            "baseline-learning phase, before any detector exists.",
        ],
        reading=[
            _r("Observations fed", fed, "shared across all twins"),
            _r("Twins ready", f"{ready}/{total}",
               f"ready means at least {min_fit} observations",
               "all ready" if all_ready else "some still warming"),
        ],
        matters=(
            "From Step 5 onward this trust is withdrawn. Once the twins are "
            "armed, any observation the twin or the model judges hostile is "
            "refused entry to the twin's history. An attacker who can teach a "
            "twin that an attack is normal has beaten the system before the "
            "classifier ever runs -- so that gate matters more than it looks."),
        nxt=("Move to Step 4 and fit the forward models."
             if all_ready else
             "Collect more telemetry in Step 2, then feed the twins again."),
        next_step=4 if all_ready else 2,
        tone="good" if all_ready else "warn")


# ---------------------------------------------------------------------------
# STEP 4 -- prediction
# ---------------------------------------------------------------------------
def _fit_predictors(res: Dict[str, Any], p) -> Dict[str, Any]:
    fitted = res.get("fitted", [])
    preds = res.get("predictions", [])
    lags = res.get("lags", SETTINGS.twin.lags)

    biggest = None
    for row in preds:
        for c in row.get("compare", []):
            cur = c.get("current") or 0.0
            change = abs((c.get("predicted", 0.0) - cur) / (abs(cur) + 1e-9))
            if biggest is None or change > biggest[2]:
                biggest = (row["device_id"], c["feature"], change)

    happened = [
        f"Fitted a ridge-regularised vector autoregression for each of "
        f"{_plural(len(fitted), 'twin')}, using the last {lags} observations "
        f"as context.",
        "Each fit also measured its own residual spread -- how wrong the model "
        "usually is on that particular device.",
    ]
    if biggest:
        happened.append(
            f"Largest expected move: {biggest[1].replace('_', ' ')} on "
            f"{biggest[0]}, about {biggest[2] * 100:.0f}% from its current value.")

    return _card(
        headline=f"Forward models fitted for {_plural(len(fitted), 'device')}.",
        happened=happened,
        reading=[
            _r("Predictors fitted", len(fitted), "one per ready twin"),
            _r("Lags used", lags, "how many past observations feed each forecast"),
        ],
        matters=(
            "The residual spread is the important output here, not the point "
            "forecast. It is what gives every device its own tolerance: a "
            "rock-steady temperature sensor gets a tight cone and a bursty "
            "smart speaker a wide one. That is what stops the consistency score "
            "in Step 5 from being a single one-size-fits-all threshold that is "
            "either deaf on noisy devices or hysterical on quiet ones."),
        nxt="Move to Step 5 and commit these forecasts as counterfactual futures.",
        next_step=5, tone="good")


# ---------------------------------------------------------------------------
# STEP 5 -- counterfactual futures
# ---------------------------------------------------------------------------
def _generate_futures(res: Dict[str, Any], p) -> Dict[str, Any]:
    armed = res.get("armed", [])
    skipped = res.get("skipped", [])
    n_f = res.get("n_futures", SETTINGS.twin.n_futures)
    horizon = res.get("horizon", SETTINGS.twin.horizon)
    total = len(armed) * n_f * horizon

    return _card(
        headline=f"{_plural(len(armed), 'twin')} committed to "
                 f"{n_f} futures each.",
        happened=[
            f"Rolled out {n_f} trajectories per twin, {horizon} ticks ahead -- "
            f"{total} predicted states in total.",
            "Each trajectory is one way this device could plausibly behave if "
            "it carried on being itself, sampled from the residual spread "
            "measured in Step 4.",
            "These are now frozen. The observation they will be judged against "
            "does not exist yet.",
        ] + ([f"{len(skipped)} twin(s) skipped for lack of history."]
             if skipped else []),
        reading=[
            _r("Twins armed", len(armed), "each holds its own committed futures"),
            _r("Futures per twin", n_f, "more futures means a smoother envelope"),
            _r("Horizon", f"{horizon} ticks", "how far ahead each one runs"),
        ],
        matters=(
            "The ordering is the whole point, and it is what separates this "
            "from anomaly detection. Because the futures were committed before "
            "the next observation was produced, comparing them is a genuine "
            "prediction test. A model that fits an explanation to data it has "
            "already seen can rationalise anything; one that has to commit "
            "first cannot."),
        nxt="Take a live tick and score reality against this commitment.",
        next_step=5, tone="good")


def _counterfactual_check(res: Dict[str, Any], p) -> Dict[str, Any]:
    rows = res.get("rows", [])
    flagged = res.get("flagged", 0)
    threshold = res.get("threshold", SETTINGS.validate.obs_anomaly_threshold)
    scores = [r["consistency"] for r in rows] or [0.0]
    worst = min(rows, key=lambda r: r["consistency"]) if rows else None
    planes = sorted({pl for r in rows for pl in r.get("anomalous_planes", [])})
    truth_attacked = [r for r in rows if r.get("ground_truth") != "normal"]

    happened = [
        f"Took one live tick and scored all {len(rows)} devices against the "
        f"futures committed a moment ago.",
        f"Consistency ranged from {min(scores):.3f} to {max(scores):.3f}; "
        f"anything under {threshold} is flagged.",
    ]
    if worst is not None:
        happened.append(
            f"Lowest was {worst['device_id']} at {worst['consistency']:.3f} "
            f"({worst['deviation']:.2f} sigma from its predicted envelope).")
    if planes:
        happened.append(
            f"Planes showing strain: {', '.join(planes)}. The plane that moves "
            f"tells you what kind of attack it is, not merely that one occurred.")
    happened.append(
        "Flagged observations were refused entry to their twin's history; "
        "consistent ones were folded in.")

    if truth_attacked:
        caught = sum(1 for r in truth_attacked if r["flagged"])
        tone = "good" if caught == len(truth_attacked) else "bad"
        headline = (f"{caught} of {len(truth_attacked)} devices actually under "
                    f"attack were flagged.")
    elif flagged:
        tone = "warn"
        headline = (f"{flagged} deviation(s) flagged on traffic that is "
                    f"genuinely healthy -- a false alarm.")
    else:
        tone = "good"
        headline = "All devices behaved within their committed envelopes."

    return _card(
        headline=headline,
        happened=happened,
        reading=[
            _r("Flagged", f"{flagged}/{len(rows)}",
               "consistency below the anomaly threshold"),
            _r("Lowest consistency", f"{min(scores):.3f}",
               "1.0 is a perfect match to the prediction"),
            _r("Threshold", threshold, "tuned so healthy traffic sits above it"),
        ],
        matters=(
            "A healthy fleet should produce no flags at all here. That is the "
            "baseline you need before Step 6, because the twin's disagreement "
            "with the classifier is the signal the self-healing monitor watches "
            "in Step 12 -- and a twin that cries wolf makes that signal "
            "worthless."),
        nxt=("Run it again to build confidence, or move to Step 6 and train "
             "the detector."),
        next_step=6, tone=tone)


# ---------------------------------------------------------------------------
# STEP 6 -- detection
# ---------------------------------------------------------------------------
def _build_corpus(res: Dict[str, Any], p) -> Dict[str, Any]:
    c = res.get("corpus", {})
    return _card(
        headline=f"Generated a {c.get('rows', 0)}-row labelled corpus.",
        happened=[
            f"Rows were generated from the profiles of the devices you actually "
            f"deployed, balanced across all seven threat classes.",
            f"Split into {c.get('train_rows', 0)} training rows, "
            f"{c.get('eval_rows', 0)} held out for the promotion gates, and "
            f"{c.get('core_rows', 0)} kept as a trusted reference core.",
            "Attack rows were drawn across a range of intensities, not only at "
            "full strength.",
        ],
        reading=[
            _r("Total rows", c.get("rows", 0), "balanced across seven classes"),
            _r("Evaluation set", c.get("eval_rows", 0),
               "never trained on; the gates in Step 11 score against it"),
            _r("Trusted core", c.get("core_rows", 0),
               "what shadow models in Step 8 are grafted onto"),
        ],
        matters=(
            "The intensity range matters more than the row count. Training only "
            "on loud attacks produces a model that is flawless in a "
            "demonstration and blind to anything subtle -- and subtle is "
            "exactly what a competent attacker does. The held-out split matters "
            "for the same honesty reason: a model scored on its own training "
            "data tells you nothing."),
        nxt="Train the detector on this corpus.",
        next_step=6, tone="good")


def _train_detector(res: Dict[str, Any], p) -> Dict[str, Any]:
    m = res.get("metrics", {})
    fnr = m.get("false_negative_rate", 0.0)
    fpr = m.get("false_positive_rate", 0.0)
    acc = m.get("accuracy", 0.0)
    worst = min(((k, v.get("recall") or 0.0)
                 for k, v in m.get("per_class", {}).items()),
                key=lambda kv: kv[1], default=("", 1.0))
    top = (res.get("importances") or [{}])[0].get("feature", "")

    happened = [
        f"Trained model v{res.get('version')} on {m.get('n_train', 0)} rows in "
        f"{res.get('elapsed_s', 0)}s, then scored it on "
        f"{m.get('n_eval', 0)} rows it had never seen.",
        f"Weakest class is {worst[0].replace('_', ' ')} at "
        f"{_pct(worst[1], 0)} recall -- that is where this model is most likely "
        f"to miss something.",
    ]
    if top:
        happened.append(f"The feature it leans on most is {top}.")
    happened.append(
        "The validator's physics reference was calibrated from this same "
        "trusted data, per threat class.")

    tone = "good" if fnr < 0.08 and fpr < 0.10 else "warn"

    return _card(
        headline=f"Detector v{res.get('version')} trained -- "
                 f"{_pct(acc)} accuracy.",
        happened=happened,
        reading=[
            _r("Accuracy", _pct(acc), "overall, across all seven classes"),
            _r("False negatives", _pct(fnr),
               "attacks called benign -- the failure mode poisoning is built to "
               "produce, so this is the number to watch",
               "acceptable" if fnr < 0.08 else "high"),
            _r("False positives", _pct(fpr),
               "benign traffic called an attack -- the number that gets a "
               "security system switched off by an irritated owner",
               "acceptable" if fpr < 0.10 else "high"),
        ],
        matters=(
            "Accuracy is the least interesting number on this card. A backdoored "
            "model scores beautifully on accuracy -- that is precisely the point "
            "of a backdoor. The two error rates, and the poison resistance "
            "measured in Step 9, are what actually tell you whether the model "
            "can be trusted."),
        nxt="Launch an attack by hand, then run the monitor to watch both "
            "detectors respond.",
        next_step=6, tone=tone)


def _launch_attack(res: Dict[str, Any], p) -> Dict[str, Any]:
    d = res.get("device", {})
    attack = d.get("attack", "")
    return _card(
        headline=f"{attack.replace('_', ' ').title()} launched against "
                 f"{d.get('device_id')}.",
        happened=[
            f"The device will emit deformed telemetry for the next "
            f"{d.get('attack_ticks_left', 0)} ticks, at intensity "
            f"{d.get('intensity')}.",
            "The attack ramps in over the first few ticks rather than "
            "appearing instantly at full volume.",
            "Nothing has been detected yet -- detection only happens when you "
            "run the monitor.",
        ],
        reading=[
            _r("Target", d.get("device_id", ""), "one device, chosen by you"),
            _r("Attack", attack, "deforms specific holographic planes"),
            _r("Ticks remaining", d.get("attack_ticks_left", 0),
               "it expires on its own"),
        ],
        matters=(
            "The simulator records the ground truth so the console can score "
            "the defence afterwards, but neither the twin nor the model is ever "
            "shown it. Every verdict you are about to see was reached from the "
            "telemetry alone."),
        nxt="Run the monitor and compare what the twin and the model each say.",
        next_step=6, tone="warn")


def _monitor(res: Dict[str, Any], p) -> Dict[str, Any]:
    rows = res.get("all_rows", []) or res.get("rows", [])
    ticks = res.get("ticks", 0)
    attacked = [r for r in rows if r.get("ground_truth") != "normal"]
    benign = [r for r in rows if r.get("ground_truth") == "normal"]
    caught = [r for r in attacked if r.get("predicted") != "normal"]
    false_alarms = [r for r in benign if r.get("predicted") != "normal"]
    twin_and_model = [r for r in attacked
                      if r.get("twin_flagged") and r.get("predicted") != "normal"]

    happened = [
        f"Ran {_plural(ticks, 'tick')} through the full gateway path: the twin "
        f"scored each observation against its committed futures, the model "
        f"classified it, and the health monitor recorded whether they agreed.",
    ]
    if attacked:
        cf = [r["consistency"] for r in attacked]
        happened.append(
            f"Of {len(attacked)} observations from devices genuinely under "
            f"attack, the model caught {len(caught)} and the twin independently "
            f"flagged {sum(1 for r in attacked if r.get('twin_flagged'))}.")
        happened.append(
            f"Twin consistency on attacked devices fell to "
            f"{min(cf):.3f}-{max(cf):.3f}, against roughly 0.5-0.9 for healthy "
            f"traffic.")
    if false_alarms:
        happened.append(
            f"{len(false_alarms)} healthy observation(s) were misread as an "
            f"attack.")
    happened.append(
        "Every observation either detector distrusted was refused entry to its "
        "twin's history.")

    if attacked:
        rate = len(caught) / len(attacked)
        tone = "good" if rate >= 0.8 else "bad"
        headline = (f"Caught {len(caught)} of {len(attacked)} attack "
                    f"observations ({_pct(rate, 0)}).")
    else:
        tone = "warn" if false_alarms else "good"
        headline = (f"{len(false_alarms)} false alarm(s) on healthy traffic."
                    if false_alarms else
                    "All quiet -- no attacks running and nothing flagged.")

    reading = [_r("Observations", len(rows), f"across {ticks} tick(s)")]
    if attacked:
        reading.append(_r("Attack recall", _pct(len(caught) / len(attacked), 0),
                          "model verdicts on genuinely hostile traffic"))
        reading.append(_r("Both detectors agreed", len(twin_and_model),
                          "twin and model independently flagged the same rows"))
    reading.append(_r("False alarms", len(false_alarms),
                      "healthy traffic called hostile"))

    return _card(
        headline=headline, happened=happened, reading=reading,
        matters=(
            "The agreement between the twin and the model is the quantity that "
            "makes Step 12 possible. They are independent detectors of the same "
            "events -- the twin judges against its own forecast, the model "
            "against what it learned. When a poisoned model later goes quiet "
            "while the twin keeps flagging, that divergence is the only "
            "unlabelled evidence of compromise available."),
        nxt="Move to Step 7 and craft a poisoned training contribution.",
        next_step=7, tone=tone)


# ---------------------------------------------------------------------------
# STEP 7 -- poisoning
# ---------------------------------------------------------------------------
def _craft_update(res: Dict[str, Any], p) -> Dict[str, Any]:
    strategy = res.get("strategy", "")
    created = res.get("created", [])
    text = STRATEGY_TEXT.get(strategy, {})
    rows = sum(c.get("n_samples", 0) for c in created)
    labels = created[0].get("labels", {}) if created else {}
    normal_share = (labels.get("normal", 0) / max(sum(labels.values()), 1)
                    if labels else 0.0)

    happened = [
        f"Built {_plural(len(created), 'update')} totalling {rows} rows: "
        f"{text.get('detail', '')}",
        f"The first update declares {labels.get('normal', 0)} of its rows "
        f"normal ({_pct(normal_share, 0)} of the payload).",
        "Nothing has been validated, trained on, or applied. The update is "
        "sitting in the inbox doing nothing at all.",
    ]
    if strategy == "sybil":
        happened.append(
            f"The payload was deliberately split across {len(created)} small "
            f"updates from {len(created)} invented device identities, so no "
            f"single contribution looks big enough to be worth auditing.")
    elif strategy == "clean_label":
        happened.append(
            "Note that no label was altered. Every label in this update is "
            "honest, which is what makes it invisible to distributional checks.")
    elif strategy == "clean":
        happened.append(
            "This is the control case. If the gate in Step 8 rejects this, the "
            "gate is miscalibrated and the whole result is worthless.")

    return _card(
        headline=(f"Crafted {_plural(len(created), 'update')} using "
                  f"{text.get('label', strategy)}."),
        happened=happened,
        reading=[
            _r("Updates created", len(created),
               "sybil produces many; the others produce one"),
            _r("Rows", rows, "the size of the training contribution"),
            _r("Declared normal", _pct(normal_share, 0),
               "compare this against the trusted prior of about 14%"),
        ],
        matters=(
            "In a federated consumer-IoT deployment, contributions like this "
            "arrive from devices, hubs or a vendor cloud -- any of which may be "
            "attacker-controlled. The console records what the update really is "
            "so you can score the defence afterwards, but the validator in Step "
            "8 never sees that tag."),
        nxt="Go to Step 8, make sure the bank and gate are ready, then validate it.",
        next_step=8, tone="warn" if strategy != "clean" else "info")


# ---------------------------------------------------------------------------
# STEP 8 -- validation
# ---------------------------------------------------------------------------
def _refresh_bank(res: Dict[str, Any], p) -> Dict[str, Any]:
    b = res.get("bank", {})
    return _card(
        headline=f"Audit bank rebuilt -- {b.get('n', 0)} scenarios.",
        happened=[
            f"{b.get('benign', 0)} benign futures were taken straight from the "
            f"twins' commitments.",
            f"{b.get('attack', 0)} attack-conditioned futures were built by "
            f"applying each attack class's deformation on top of those same "
            f"futures.",
            "Scenarios the current trusted model already gets wrong were "
            "filtered out.",
        ],
        reading=[
            _r("Scenarios", b.get("n", 0), "each has a known correct answer"),
            _r("Benign", b.get("benign", 0), "should still be called normal"),
            _r("Attack-conditioned", b.get("attack", 0),
               "should still be called an attack"),
        ],
        matters=(
            "The filtering is what makes the score in a moment mean something "
            "precise. Left unfiltered, the bank carries the trusted model's own "
            "mistakes as noise, and every update inherits that noise -- which is "
            "exactly the margin a subtle poisoning attack hides inside. "
            "Filtered, any degradation is attributable to the update and "
            "nothing else."),
        nxt="Calibrate the accept gate on honest updates.",
        next_step=8, tone="good")


def _calibrate_gate(res: Dict[str, Any], p) -> Dict[str, Any]:
    c = res.get("calibration", {})
    mean = c.get("honest_mean", 0.0)
    spread = c.get("spread_used", c.get("honest_std", 0.0))
    thr = c.get("threshold", 0.0)
    z = c.get("z", SETTINGS.validate.threshold_z)

    return _card(
        headline=f"Accept gate calibrated to {_num(thr)}.",
        happened=[
            f"Generated {c.get('honest_updates', 0)} honest contributions from "
            f"held-out telemetry and scored each one against the bank.",
            f"They scored a mean of {_num(mean)} with a spread of "
            f"{_num(c.get('honest_std', 0.0))}.",
            f"Threshold = {_num(mean)} - {z} x {_num(spread)} = "
            f"{_num(c.get('raw_threshold', thr))}, then clipped to {_num(thr)}.",
        ],
        reading=[
            _r("Honest mean CCS", _num(mean), "what a legitimate update scores"),
            _r("Spread", _num(c.get("honest_std", 0.0)),
               "how much honest updates vary between themselves"),
            _r("Accept threshold", _num(thr),
               f"{z} spreads below the honest mean"),
        ],
        matters=(
            "The threshold is derived from this fleet rather than hard-coded, "
            "which is the difference between a defence that transfers to a new "
            "network and one that only works on the author's laptop. A floor is "
            "applied to the spread on purpose: calibration updates all come from "
            "one pool, so their measured variation understates what honest "
            "traffic really varies by once the fleet drifts, and without the "
            "floor the gate lands inside the honest distribution and starts "
            "rejecting legitimate contributions on day two."),
        nxt="Validate the update waiting in the inbox.",
        next_step=8, tone="good")


def _validate_update(res: Dict[str, Any], p) -> Dict[str, Any]:
    r = res.get("report", {})
    e = r.get("evidence", {})
    passed = r.get("decision") == "ACCEPTED"
    ccs = r.get("consistency_score", 0.0)
    thr = r.get("threshold", 0.0)
    margin = e.get("margin", ccs - thr)

    comps = {
        "attack_agreement": ("Attack agreement",
                             "attack scenarios the model would still catch"),
        "benign_agreement": ("Benign agreement",
                             "benign futures still called benign"),
        "stability": ("Stability", "verdicts not downgraded vs the trusted model"),
        "plane_coherence": ("Plane coherence",
                            "rows obeying the physics of their declared class"),
        "label_integrity": ("Label integrity",
                            "label mix not drifted benign-ward"),
        "label_agreement": ("Label agreement",
                            "labels matching the trusted model's own reading"),
    }
    contributions = e.get("contributions", {})
    weights = e.get("weights", {})
    # The component that cost the most score relative to a perfect one.
    losses = {k: weights.get(k, 0.0) - contributions.get(k, 0.0)
              for k in comps if k in weights}
    driver = max(losses, key=lambda k: losses[k]) if losses else None

    happened = [
        f"Grafted the update onto the trusted core, trained a shadow model, and "
        f"put it in front of all {e.get('bank_n', 0)} bank scenarios "
        f"({e.get('elapsed_ms', 0)} ms).",
        f"Counterfactual Consistency Score came out at {_num(ccs)} against a "
        f"gate of {_num(thr)} -- {'clearing' if passed else 'missing'} it by "
        f"{abs(margin):.3f}.",
    ]
    if driver:
        label, meaning = comps[driver]
        happened.append(
            f"The component that drove the decision was {label.lower()} at "
            f"{_num(e.get(driver, 0.0))} (weight {weights.get(driver, 0):.2f}) "
            f"-- {meaning}.")

    lost = {k: v for k, v in (e.get("bank_per_class") or {}).items()
            if k != "normal" and v < 0.9}
    if lost:
        worst_cls = min(lost, key=lambda k: lost[k])
        happened.append(
            f"Accepting it would leave only {_pct(lost[worst_cls], 0)} of "
            f"{worst_cls.replace('_', ' ')} scenarios still detected.")

    if e.get("novelty_penalty"):
        happened.append(
            f"The gate was tightened by {_num(e['novelty_penalty'], 2)} because "
            f"this source has never been seen before and arrived amid a burst "
            f"of other new identities -- the structural signature of a sybil "
            f"flood.")

    truth = r.get("declared_strategy", "clean")
    guess = r.get("suspected_strategy", "")
    correct_decision = (passed and truth == "clean") or \
                       (not passed and truth != "clean")
    happened.append(
        f"Attribution says {guess.replace('_', ' ')}; the update really was "
        f"{truth.replace('_', ' ')}"
        f"{' -- matched' if guess == truth else ''}.")

    return _card(
        headline=(f"{'Accepted' if passed else 'Quarantined'} at CCS "
                  f"{_num(ccs)} (gate {_num(thr)})."),
        happened=happened,
        reading=[
            _r("CCS", _num(ccs), "weighted sum of six components",
               "above gate" if passed else "below gate"),
            _r("Margin", f"{margin:+.3f}", "distance from the accept threshold"),
            _r("Source reputation", _num(r.get("reputation", 1.0)),
               f"an EWMA of this source's history; floor is "
               f"{_num(e.get('reputation_floor', 0.7), 2)}"),
            _r("Decision was", "correct" if correct_decision else "WRONG",
               "measured against the ground truth the simulator recorded",
               "correct" if correct_decision else "wrong"),
        ],
        matters=(
            "This is the framework's actual contribution. A conventional "
            "defence asks whether the update looks like the others -- a question "
            "about the past, and one an attacker answers by staying close to "
            "the crowd. This asks what accepting it would cost against futures "
            "the twins committed to before the update existed. Nothing has been "
            "applied yet: the verdict is a recommendation until you act on it."),
        nxt=("Apply the decision below, or override it -- both are recorded."),
        next_step=8,
        # Green means all clear, amber means something hostile was caught and
        # handled, red means the gate got it wrong. Colouring a correctly
        # quarantined poison green would be technically defensible and read
        # completely backwards to an operator scanning the page.
        tone=("bad" if not correct_decision
              else "good" if passed else "warn"))


def _apply_decision(res: Dict[str, Any], p) -> Dict[str, Any]:
    decision = res.get("decision", "")
    accepted = decision == "ACCEPTED"
    return _card(
        headline=(f"Update {'accepted into the safe pool' if accepted else 'held in quarantine'}"
                  f"{' by operator override' if res.get('overridden') else ''}."),
        happened=[
            (f"Its rows joined the training pool, which now holds "
             f"{res.get('pool_size', 0)} rows."
             if accepted else
             "It is held intact, out of the training pool, with the report that "
             "condemned it."),
            ("Each row remembers which update and which source contributed it."
             if accepted else
             "Nothing was deleted -- a quarantined update can be dissected in "
             "Step 10 and re-judged later against a better bank."),
        ] + (["You overrode the automatic verdict. That is recorded in the "
              "activity log."] if res.get("overridden") else []),
        reading=[
            _r("Decision", decision, "what was actually applied"),
            _r("Safe pool", res.get("pool_size", 0),
               "only validated rows are ever trained on"),
            _r("Held in quarantine", (res.get("quarantine") or {}).get("held", 0),
               "awaiting analysis or release"),
        ],
        matters=(
            "Provenance is why the accept side is safe to get wrong "
            "occasionally. Because every pooled row remembers its contributor, "
            "Step 12 can excise one hostile source surgically instead of "
            "discarding the entire pool and starting again."),
        nxt=("Dissect what was held in Step 10, or retrain in Step 11."
             if not accepted else
             "Craft more contributions in Step 7, or retrain in Step 11."),
        next_step=10 if not accepted else 11,
        tone="warn" if not accepted else "good")


# ---------------------------------------------------------------------------
# STEP 9 -- immunization
# ---------------------------------------------------------------------------
def _generate_vaccine(res: Dict[str, Any], p) -> Dict[str, Any]:
    v = res.get("vaccine", {})
    b = v.get("breakdown", {})
    return _card(
        headline=f"Synthesised {v.get('rows', 0)} predictive vaccine rows.",
        happened=[
            f"Built from the futures the twins have already committed to, so "
            f"these describe attacks on this fleet that have not happened yet.",
        ] + [
            f"{n} {k} rows: " + {
                "boundary": "weak but genuine attacks, labelled honestly",
                "relabel": "ordinary-strength attacks with correct labels",
                "trigger": "attack rows with arbitrary features pinned to "
                           "constants",
            }.get(k, "") for k, n in b.items()
        ] + [
            "Every vaccine row is labelled as an attack. None of them teaches "
            "the model that an attack is normal.",
        ],
        reading=[_r(k.title(), n, "rows") for k, n in b.items()] +
                [_r("Total", v.get("rows", 0), "folded into the next retrain")],
        matters=(
            "This is the only part of the framework that moves first. The "
            "trigger vaccine is the subtle one and worth being precise about: "
            "it does not use the attacker's actual trigger, because we do not "
            "know it and a vaccine built from a known secret would prove "
            "nothing. It teaches the general lesson that pinning odd constant "
            "values onto a row does not make the row benign, so an arbitrary "
            "trigger gets no free ride."),
        nxt="Measure how much poisoning the current pool can absorb.",
        next_step=9, tone="good")


def _measure_resistance(res: Dict[str, Any], p) -> Dict[str, Any]:
    r = res.get("resistance", {})
    score = r.get("poison_resistance", 0.0)
    floor = SETTINGS.retrain.min_poison_resistance
    per = r.get("per_strategy", {})
    weakest = r.get("weakest", "")
    passes = score >= floor

    return _card(
        headline=f"Poison resistance {_num(score)} "
                 f"({'above' if passes else 'below'} the {floor} gate).",
        happened=[
            f"For each of {len(per)} strategies: crafted the poison, grafted it "
            f"onto the current pool at a realistic federated share, retrained a "
            f"probe, and measured how many of the "
            f"{r.get('scenarios_tested', 0)} attack scenarios survived.",
            f"Weakest against {weakest.replace('_', ' ')} at "
            f"{_pct(per.get(weakest, 0.0), 1)} surviving detection.",
            f"Strongest against "
            f"{max(per, key=lambda k: per[k]).replace('_', ' ')}."
            if per else "",
        ],
        reading=[_r(k.replace('_', ' ').title(), _pct(v, 1),
                    "attack detection surviving this poison")
                 for k, v in per.items()] +
                [_r("Overall", _num(score), f"gate is {floor}",
                    "pass" if passes else "fail")],
        matters=(
            "This is the gate that catches a backdoor. A backdoored model "
            "scores beautifully on accuracy -- that is the entire point of a "
            "backdoor -- so an accuracy-only promotion gate waves it through "
            "without hesitation. The share matters too: at its natural ratio "
            "the rehearsed poison is a few percent of the probe's data, every "
            "model scores about 0.97, and the metric ranks nothing."),
        nxt="Retrain in Step 11 -- this number is one of the four gates.",
        next_step=11, tone="good" if passes else "bad")


# ---------------------------------------------------------------------------
# STEP 10 -- quarantine
# ---------------------------------------------------------------------------
def _analyse(res: Dict[str, Any], p) -> Dict[str, Any]:
    a = res.get("analysis", {})
    findings = a.get("findings", [])
    return _card(
        headline=f"Analysis complete -- suspected "
                 f"{a.get('suspected_strategy', '').replace('_', ' ')}.",
        happened=[f"Produced {_plural(len(findings), 'finding')} from the "
                  f"update's own rows and its validation evidence."]
                 + findings[:4],
        reading=[
            _r("Suspected strategy",
               a.get("suspected_strategy", "").replace("_", " "),
               f"at {_pct(a.get('strategy_confidence', 0), 0)} confidence"),
            _r("Rows examined", a.get("n_samples", 0),
               "the update is held intact, not deleted"),
            _r("Most anomalous rows", len(a.get("suspicious_rows", [])),
               "ranked by how far their physics deviate"),
        ],
        matters=(
            "Attribution here is rule-based rather than learned, and that is a "
            "deliberate limitation rather than a shortcut: a learned attributor "
            "would need labelled poison to train on, and if we had that we would "
            "not need the defence. The rules encode the structural fingerprint "
            "each strategy cannot avoid leaving. All five scores are shown so "
            "you can disagree with the ranking."),
        nxt="Release it if you judge it honest, or leave it held and retrain "
            "without it.",
        next_step=11, tone="info")


def _rescore(res: Dict[str, Any], p) -> Dict[str, Any]:
    r = res.get("rescore", {})
    would = r.get("would_pass", [])
    return _card(
        headline=(f"{len(would)} of {r.get('rescored', 0)} held updates would "
                  f"now pass."),
        happened=[
            "Re-ran validation on everything currently held, against the "
            "bank as it stands now rather than as it stood when they were "
            "rejected.",
            ("Nothing was released automatically -- releasing is your call."
             if not r.get("auto_released") else
             f"{len(would)} update(s) were released into the safe pool."),
        ],
        reading=[
            _r("Rescored", r.get("rescored", 0), "everything still held"),
            _r("Would now pass", len(would),
               "the bank has improved since they were judged"),
            _r("Still held", len(r.get("still_held", [])),
               "rejected again on the current bank"),
        ],
        matters=(
            "A gate is only as good as the bank it scored against, and the bank "
            "improves every round as the twins learn the fleet. An update "
            "quarantined by a thin early bank may be perfectly honest. Holding "
            "rather than deleting is what makes that recoverable."),
        nxt="Release anything you judge honest, then retrain in Step 11.",
        next_step=11, tone="info")


def _release(res: Dict[str, Any], p) -> Dict[str, Any]:
    return _card(
        headline="Update released from quarantine into the safe pool.",
        happened=[
            f"Its rows joined the training pool, which now holds "
            f"{res.get('pool_size', 0)} rows.",
            "If this update really was hostile, the effect will show up as a "
            "failed accuracy or poison-resistance gate the next time you "
            "retrain.",
        ],
        reading=[
            _r("Safe pool", res.get("pool_size", 0), "rows available for training"),
            _r("Still held", (res.get("quarantine") or {}).get("held", 0),
               "remaining quarantined updates"),
        ],
        matters=(
            "Release is deliberately an operator action rather than an "
            "automatic one. A security control a human cannot inspect and "
            "countermand is not a control, it is an oracle -- but the promotion "
            "gates in Step 11 are still there to catch a release you should not "
            "have made."),
        nxt="Retrain in Step 11 and watch whether the gates still pass.",
        next_step=11, tone="warn")


# ---------------------------------------------------------------------------
# STEP 11 -- retraining
# ---------------------------------------------------------------------------
def _retrain(res: Dict[str, Any], p) -> Dict[str, Any]:
    o = res.get("outcome", {})
    gates = o.get("gates", {})
    failed = [k for k, g in gates.items() if not g.get("pass")]
    promoted = o.get("promoted")
    m = o.get("metrics", {})
    inc = o.get("incumbent_metrics", {})
    vac = o.get("vaccine", {})

    happened = [
        f"Trained a candidate on {o.get('pool', {}).get('training_rows', 0)} "
        f"rows in {o.get('elapsed_s', 0)}s"
        + (f", including {vac.get('rows_used', 0)} vaccine rows."
           if vac.get("rows_used") else "."),
        f"Scored it on the held-out evaluation set: {_pct(m.get('accuracy'))} "
        f"accuracy against the incumbent's {_pct(inc.get('accuracy'))}.",
    ]
    if failed:
        for name in failed:
            g = gates[name]
            happened.append(
                f"Gate '{name.replace('_', ' ')}' failed: value "
                f"{_num(g.get('value'), 4)} against its limit.")
        happened.append(
            "The candidate was discarded and the incumbent model stays in "
            "service. Nothing was installed.")
    else:
        happened.append(
            f"All four gates passed, so model v"
            f"{(o.get('version') or {}).get('version')} was promoted and is now "
            f"live.")

    return _card(
        headline=(f"Candidate promoted as v{(o.get('version') or {}).get('version')}."
                  if promoted else
                  f"Candidate rejected -- failed {', '.join(failed)}."),
        happened=happened,
        reading=[
            _r(k.replace("_", " ").title(),
               _num(g.get("value"), 4) if not isinstance(g.get("value"), int)
               else g.get("value"),
               "requirement met" if g.get("pass") else "requirement NOT met",
               "pass" if g.get("pass") else "fail")
            for k, g in gates.items()
        ],
        matters=(
            "Rejection is a successful outcome, not an error. The gates exist "
            "so that a pool which has been contaminated -- by poison that got "
            "through, or by an update you released against advice -- cannot "
            "install a worse model than the one already running. The "
            "poison-resistance gate is the one that earns its place: a "
            "backdoored candidate passes an accuracy check comfortably."),
        nxt=("Check model health in Step 12."
             if promoted else
             "Clean the pool -- quarantine the bad source, or self-heal in "
             "Step 12 -- and retrain."),
        next_step=12,
        tone="good" if promoted else "warn")


# ---------------------------------------------------------------------------
# STEP 12 -- self-healing
# ---------------------------------------------------------------------------
def _health_check(res: Dict[str, Any], p) -> Dict[str, Any]:
    c = res.get("check", {})
    if not c.get("evaluated"):
        return _card(
            headline="Not enough evidence to judge the model yet.",
            happened=[
                c.get("note", ""),
                "The monitor compares the twin and the model on observations "
                "the twin flagged. With no flags there is nothing to compare.",
            ],
            reading=[
                _r("Twin flags in window", c.get("twin_flags", 0),
                   f"at least {SETTINGS.heal.min_flags_for_verdict} are needed"),
                _r("Window", c.get("window", 0),
                   f"of {SETTINGS.heal.window} observations"),
            ],
            matters=(
                "Refusing to judge on thin evidence is the correct behaviour. A "
                "monitor that returns a confident verdict from four "
                "observations produces exactly the false rollbacks that make "
                "operators disable self-healing."),
            nxt="Run an attack in Step 6 and monitor a few ticks, then check "
                "again.",
            next_step=6, tone="info")

    degraded = c.get("degraded")
    agree = c.get("agreement")
    base = c.get("baseline_agreement")
    drop = c.get("agreement_drop")

    happened = [
        f"Over the last {c.get('window', 0)} observations the twin flagged "
        f"{c.get('twin_flags', 0)} and the model independently flagged "
        f"{c.get('model_flags', 0)}; they agreed on {c.get('both_flagged', 0)}.",
        f"Agreement is {_pct(agree, 1)}"
        + (f", against a learned baseline of {_pct(base, 1)} for this model."
           if base else " -- the baseline for this model is still being learned."),
    ]
    if drop is not None:
        happened.append(
            f"That is a {_pct(drop, 1)} change from its own baseline; "
            f"{_pct(SETTINGS.heal.max_agreement_drop, 0)} is the trigger.")
    if degraded:
        happened.extend(c.get("reasons", []))
    else:
        happened.append("No degradation signal. The model is behaving as it did "
                        "when its baseline was established.")

    return _card(
        headline=("Model health DEGRADED." if degraded else
                  f"Model healthy -- score {_num(c.get('health_score'))}."),
        happened=happened,
        reading=[
            _r("Health score", _num(c.get("health_score")),
               f"floor is {SETTINGS.heal.min_health_score}",
               "degraded" if degraded else "healthy"),
            _r("Model/twin agreement", _pct(agree, 1),
               "of what the twin flagged, how much the model also flagged"),
            _r("False negatives", _pct(c.get("false_negative_rate"), 1),
               "twin flagged it, model called it normal"),
        ],
        matters=(
            "The trigger is degradation against this model's own baseline, not "
            "an absolute rate, and that distinction is load-bearing. The twin "
            "and the classifier disagree constantly on low-and-slow attacks; "
            "that is ordinary operation. A fixed threshold would fire on a noisy "
            "healthy fleet and stay silent on a model that was mediocre to "
            "begin with. What is never normal is a model getting materially "
            "worse than it used to be."),
        nxt=("Trigger self-healing below." if degraded else
             "Nothing to do. Keep monitoring, or poison the pool and watch this "
             "number fall."),
        next_step=12, tone="bad" if degraded else "good")


def _self_heal(res: Dict[str, Any], p) -> Dict[str, Any]:
    e = res.get("event", {})
    rolled = e.get("rollback_available")
    retrain = res.get("retrain")

    happened = []
    if rolled:
        happened.append(
            f"Marked v{e.get('from_version')} untrusted and activated "
            f"v{e.get('rolled_back_to')}, the newest version still trusted.")
    else:
        happened.append(
            "There is no earlier trusted model to roll back to, so the current "
            "model stays in service while the pool is cleaned.")
    if e.get("purged_sources"):
        happened.append(
            f"Purged {e.get('purged_rows', 0)} rows contributed by "
            f"{_plural(len(e['purged_sources']), 'source')}: "
            f"{', '.join(e['purged_sources'][:4])}.")
    else:
        happened.append("No suspect sources to purge -- nothing is held in "
                        "quarantine.")
    happened.append("The health baseline was reset, because a different model "
                    "has a different normal.")
    if retrain:
        happened.append(
            f"Retrained on the cleaned pool: "
            f"{'promoted' if retrain.get('promoted') else 'candidate rejected'}.")

    return _card(
        headline=(f"Rolled back to v{e.get('rolled_back_to')} and cleaned the pool."
                  if rolled else "Pool cleaned; no rollback target available."),
        happened=happened,
        reading=[
            _r("Rolled back to",
               f"v{e.get('rolled_back_to')}" if rolled else "n/a",
               f"from v{e.get('from_version')}" if rolled
               else "no earlier trusted version exists"),
            _r("Rows purged", e.get("purged_rows", 0),
               "removed by contributor, not wholesale"),
            _r("Pool after", e.get("pool_after", 0), "rows remaining"),
        ],
        matters=(
            "Healing is rollback, purge, retrain -- in that order, and never in "
            "place. You cannot subtract poison from a trained model; you can "
            "only return to something you trust and rebuild from a cleaned "
            "pool. That is also why the registry never overwrites a version, "
            "and why every pooled row remembers who contributed it."),
        nxt="Run a health check again to confirm the restored model behaves.",
        next_step=12, tone="warn")


def _rollback(res: Dict[str, Any], p) -> Dict[str, Any]:
    reg = res.get("registry", {})
    return _card(
        headline=f"Now running model v{reg.get('active')}.",
        happened=[
            "Activated an earlier version from the registry by hand.",
            "The health baseline was reset, because this model has its own "
            "operating point.",
            "Nothing was purged from the training pool -- this is a model "
            "switch only.",
        ],
        reading=[
            _r("Active version", f"v{reg.get('active')}", "now serving verdicts"),
            _r("Versions retained", reg.get("count", 0),
               "nothing is ever overwritten"),
        ],
        matters=(
            "Being able to name any past model and put it back is what makes "
            "the rollback in self-healing credible rather than aspirational."),
        nxt="Run a health check to confirm this model behaves as expected.",
        next_step=12, tone="info")


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
EXPLAINERS: Dict[str, Callable[[Dict[str, Any], Any], Dict[str, Any]]] = {
    "add_device": _add_device,
    "start_gateway": _start_gateway,
    "collect": _collect,
    "create_twins": _create_twins,
    "feed_twins": _feed_twins,
    "fit_predictors": _fit_predictors,
    "generate_futures": _generate_futures,
    "counterfactual_check": _counterfactual_check,
    "build_corpus": _build_corpus,
    "train_detector": _train_detector,
    "launch_attack": _launch_attack,
    "monitor": _monitor,
    "craft_update": _craft_update,
    "refresh_bank": _refresh_bank,
    "calibrate_gate": _calibrate_gate,
    "validate_update": _validate_update,
    "apply_decision": _apply_decision,
    "generate_vaccine": _generate_vaccine,
    "measure_resistance": _measure_resistance,
    "analyse": _analyse,
    "rescore": _rescore,
    "release": _release,
    "retrain": _retrain,
    "health_check": _health_check,
    "self_heal": _self_heal,
    "rollback": _rollback,
}


def explain(action: str, result: Dict[str, Any], pipeline) -> Optional[Dict[str, Any]]:
    """Build the post-run explanation for one completed action.

    Returns ``None`` for actions with nothing worth saying.  A failure to
    explain must never break the action it is describing, so anything thrown
    while formatting is swallowed and reported in place of the card.
    """
    fn = EXPLAINERS.get(action)
    if fn is None:
        return None
    try:
        card = fn(result, pipeline)
        card["action"] = action
        card["what_happened"] = [s for s in card.get("what_happened", []) if s]
        return card
    except Exception as exc:                                # pragma: no cover
        return {"action": action, "headline": "Explanation unavailable.",
                "what_happened": [f"{type(exc).__name__}: {exc}"],
                "reading": [], "why_it_matters": "", "next": "",
                "next_step": None, "tone": "info"}
