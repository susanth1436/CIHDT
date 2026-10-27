# CIHDT — Counterfactual Immunization of Holographic Digital Twins

**Predictive Edge AI Retraining for Real-Time Threat Detection in Consumer IoT Networks**

### 🌐 [susanth1436.github.io/CIHDT](https://susanth1436.github.io/CIHDT/)

The project site: the mechanism, the architecture, the validation results, and
the report and Review-3 deck to download. It is documentation — GitHub Pages
serves static files, and the console trains models on request and holds
server-side sessions, so the console itself runs from the commands below.

A working implementation of the twelve-step framework, built as a **manual
operator console**. You choose the devices. You run every step yourself. Nothing
happens on its own.

---

## Quick start

```bash
pip install -r requirements.txt
```

```bash
python run.py
```

Then open **http://127.0.0.1:8000**. The console asks one question before
Step 1: should it read a **simulated fleet**, or the **real USB devices
attached to this machine**?

Prefer the terminal?

```bash
python cli.py --walk
```

Run the tests:

```bash
python -m pytest
```

---

## The manual contract

This is the design decision everything else follows from: **there is no
background thread, no scheduler, and no autopilot anywhere in the project.**

* The fleet emits telemetry only when you press *Collect*.
* Twins learn only when you press *Feed*.
* A model is trained only when you press *Train*.
* A poisoned update is crafted only when you craft it, validated only when you
  validate it, and applied to the system only when you apply it — and you can
  overrule the verdict in either direction.

Two things follow. Pedagogically, every arrow in the architecture diagram is a
button, so you can stop between any two stages and inspect exactly what crossed
the boundary. Practically, each step declares its prerequisites, so attempting
one out of order fails with a message naming the step that has to happen first
rather than quietly producing a meaningless result.

That matters most for the ordering the security actually depends on: **futures
must be committed before the observation they will judge exists.**

---

## Signing in

Everyone who uses the console signs in **with their email address**. It trains
models, accepts training contributions and can roll a deployed model back, so
it is not left open to whoever can reach the port.

On first start, if no account exists, one is created and its password and a
registration code are printed **once** to the terminal that started the server:

```
  A console account has been created, because none existed.

     email      operator@cihdt.local
     password   kxfp-9mwn-qtbr-3jhd

  Anyone can create their own account at /register with an
  email and a password.
```

There is deliberately **no default password in this source tree** — a shipped
credential is a credential in every deployment that forgets to change it. Set
`CIHDT_ADMIN_EMAIL` and `CIHDT_ADMIN_PASSWORD` to choose your own.

### Creating an account

`/register` lets anyone create their own account with an email address and a
password, and the sign-in page links to it. No invitation, no code: on a
console a small team runs locally, passing a secret around to enrol buys
nothing.

It is worth knowing what that gives up. This console trains models, accepts
training contributions and can roll a deployed model back, so anywhere it is
reachable by people who should not operate it, open enrolment makes the
sign-in page a formality. If that ever becomes true:

```bash
CIHDT_REQUIRE_REGISTRATION_CODE=1 python run.py
```

Sign-up then asks for a shared code, which is printed at startup and shown on
the Accounts page to anyone already signed in. Nothing else changes.

### What the implementation is careful about

* **Passwords are never stored.** Only a PBKDF2-HMAC-SHA256 derivation,
  240,000 iterations, with a per-user random salt. Verification is a
  constant-time comparison. A test reads the raw database bytes and asserts the
  plaintext is not among them.
* **The gate covers the API, not only the pages.** Every operator action has a
  JSON endpoint behind it, so a login screen guarding only the HTML would guard
  nothing. `/api/...` answers `401` without a session.
* **Sign-in failures say one thing.** "Those credentials were not recognised",
  whether the address is unknown or the password is wrong — a different answer
  for each would enumerate accounts. A missing account still costs a full key
  derivation, so the two cannot be told apart by timing either.
* **Addresses are normalised.** `Susanth@VIT.ac.in` and `susanth@vit.ac.in` are
  the same account, so case cannot be used to create a near-duplicate.
* **`next=` cannot leave the site.** An open redirect would let a crafted
  sign-in link bounce an operator somewhere hostile with the console's apparent
  blessing.
* Five wrong guesses pause an account for a minute.

Accounts are managed at `/accounts`, and every action — including refused
sign-ins and refused registrations — is recorded at `/activity`.

---

## The database

SQLite, through the standard library, in `data/cihdt.sqlite3`.

That is a deliberate choice rather than a shortcut, and it follows the same
constraint as the rest of the project: this console is meant to run on an edge
gateway where everything stays on the local network. A client/server database
would add a process to install, a port to listen on and a network dependency,
to a system whose selling point is not having one.

It is still a database used properly — the schema is versioned and migrated on
open, foreign keys are enforced (SQLite ignores them unless asked), write-ahead
logging means a reader never blocks a writer, every statement is parameterised,
and each thread gets its own connection because FastAPI runs blocking work in a
thread pool.

| Table | Holds |
|---|---|
| `users` | accounts, keyed by email, and their password derivations |
| `sessions` | live sessions, so a server restart does not sign everyone out mid-walkthrough |
| `audit_log` | every operator action, with the account that ran it and whether it succeeded |
| `settings` | small persisted values, such as the registration code |

The schema is at **v2**. The migration from v1 is a real one — it renames the
identity column from `username` to `email` across three tables, backfills
pre-email accounts, and adds `settings`. Each version runs in its own
transaction: the first attempt at v2 failed on a foreign-key constraint
(existing sessions pointed at the identity being renamed) and the database
rolled back to v1 intact rather than ending up half-migrated. The fix is in the
migration itself — it ends open sessions first, which is the correct behaviour
anyway, since the identity someone signed in with no longer exists.

The audit trail is the part worth demonstrating. A security console that cannot
say *who rolled the model back* is missing the first record an incident review
would ask for. Refused actions are kept too — an attempt that was blocked is as
interesting as one that succeeded:

```
step4/fit       refused   operator   Step 3 (Build holographic digital twins) has not...
step3/create    ok        operator   3 twin(s)
step2/collect   ok        operator   6 ticks collected
```

An existing `data/users.json` from before the database is imported on first
open and kept as `.imported`, so upgrading loses nobody's account.

If this ever has to move to PostgreSQL or MySQL, the work is confined to
[`cihdt/server/db.py`](cihdt/server/db.py): nothing above it writes SQL.

**The pipeline state is deliberately not in the database.** Twins, committed
futures and the training pool live in memory, and promoted models on disk via
the registry. That is the manual contract — a session is something you build
and can discard, not something that accumulates silently between visits.

---

## The console

The console is a **multi-page application**, and that is the same design
decision carried into the UI.

`/` is the front door: what the framework is, and the twelve steps laid out.
From there each step is a real page at its own URL — `/step/1` through
`/step/12` — and **a step page shows that step and nothing else**. There is no
rail listing the other eleven, because a page that shows you eleven other
things is a control panel, not a walkthrough.

Finishing a step is what opens the next one. The band at the foot of every step
page reads *"Step 4 is not finished yet — Step 5 is locked"* until the step's
own completion condition is met, at which point it becomes *"Step 4 complete"*
with the next step's name, its purpose, and the button that takes you there. So
the twelve are walked one page at a time, in order, and you cannot skip ahead to
a step you have not earned.

Every control is an HTML form that POSTs one operator action and then redirects
back to the step page, so:

* **a refresh re-reads the result instead of repeating the action.** In a system
  whose whole premise is that nothing happens unless you ask, the browser must
  not be able to re-fire a retrain by reloading. Post/Redirect/Get makes that
  structurally impossible rather than merely unlikely.
* **the URL is the state.** A step can be bookmarked, shared, or opened in two
  tabs, and the back button means what it says.
* **there is nothing to re-sync.** The page is rendered from the pipeline at the
  moment you asked for it.

**No JavaScript is served at all.** The whole front end is
[`cihdt/server/pages.py`](cihdt/server/pages.py), the HTML primitives in
[`cihdt/server/html.py`](cihdt/server/html.py), and one stylesheet — no
framework, no build step, no bundler, no webfont, no network call of any kind.
A page is a few kilobytes of markup and paints immediately, which also means
the page source is a readable record of exactly what the step produced.

The visual language is a corporate-site one rather than a dashboard one: a
white top bar, a full-bleed navy hero carrying a two-weight headline, pale
heading panels beside white content, teal square markers, and full-width navy
bands between sections. The post-run **"What just happened"** card is one of
those navy bands, so the most important prose on the page is also the most
prominent thing on it.

The JSON API at `/api/...` is unchanged and still returns `{result, state}` for
every action, so the pipeline keeps two independent faces: the pages an operator
drives, and the API the tests and the CLI speak to.

---

## Live devices

Everything after Step 0 is identical. The twelve steps do not know whether the
numbers they are reading came from a behavioural model or from the USB bus of
this laptop, which is the point: the framework was never about the simulator.

Choose **live** at `/start`, press *Scan the USB bus*, and the peripherals
actually attached appear — enrol one and it is monitored exactly as a simulated
device would be. On the development machine that is a Realtek Bluetooth radio,
an HP webcam (reporting `Error`, which is itself genuine signal) and a USB
composite device.

### What is measured, and what is not

This is the part a reviewer will press on, so it is stated plainly and the
console repeats it on the page.

**A USB webcam has no network stack.** It has no address, opens no sockets and
authenticates nobody. Eight of the sixteen features cannot be measured from
such a device even in principle. So every feature carries a provenance:

| Provenance | Count | What it means |
|---|---|---|
| `host` | 10 | Measured from this machine — CPU, memory, throughput, packet rate, the connection table. |
| `device` | 3 | Measured from the peripheral — how long it has been attached, how often it dropped, whether Windows still considers it healthy. |
| `declared` | 1 | USB bus power, read off the specification for the device class. **Not measured.** |
| `unavailable` | 2 | `failed_logins` needs the Windows Security event log and admin rights; `payload_entropy` needs a packet-capture driver. |

The two unavailable features are **held at zero and reported as missing, never
invented**. Attributing the host's network activity to the selected peripheral
is a **modelling assumption**, not a per-device measurement — justified because
a compromised webcam exfiltrates through its host's stack, but it is an
assumption and the page says so.

### Attacks and labels in live mode

Two things follow from working on real hardware, and neither is hidden.

**Attacks do not touch the hardware.** You cannot make a webcam mount a port
scan, and we would not attack an operator's devices if we could. A launched
attack applies the deformation *on top of the genuine live sample*, and every
record it produces is marked `synthetic=True`.

**Step 6 is half measured, half synthesised.** There is no honest way to obtain
labelled attack rows from a real peripheral. So the benign class is resampled
from observations the machine actually produced, and the attack classes are
those same real rows deformed by the profiles in `simulator/profiles.py`.

### One number worth reading carefully

Live detection scores **0.996 accuracy, 0.003 false negatives** — higher than
the simulated fleet's 0.957, and that is *not* evidence of a better model. It
is evidence of an easier problem.

The simulated corpus spans six device types whose baselines differ by three
orders of magnitude, so a weakly-attacked bulb genuinely resembles a healthy
camera. Live devices all sample one host, so their baselines are nearly
identical and that ambiguity disappears. The first live build scored a
meaningless **1.000**; it took resampling real observations for the benign
class and rehearsing attacks down to 2% intensity to put the hard cases back
in. A single-host baseline is a genuinely easier problem than a heterogeneous
fleet, and the report should say so.

---

## The twelve steps

Each step explains itself before you run it, and explains the result afterwards
(see [Step explanations](#step-explanations)).

| # | Step | What you do in the console |
|---|------|----------------------------|
| 1 | Create the IoT environment | Pick from six device types and add them one at a time. The mix determines what the model is later trained on. |
| 2 | Start the edge gateway | Bring the gateway up, then collect telemetry a chosen number of ticks at a time. |
| 3 | Build holographic twins | Create one twin per device and feed it the collected telemetry. |
| 4 | Predict future states | Fit each twin's forward model and see what it expects next, feature by feature. |
| 5 | Counterfactual futures | Roll out and **commit** to N futures, then take one live tick and score reality against that commitment. |
| 6 | Detect threats | Build a labelled corpus for *your* fleet, train the detector, launch attacks by hand, and monitor. |
| 7 | Simulate model poisoning | Craft an update using one of five strategies. It lands in an inbox and touches nothing. |
| 8 | Counterfactual validation | Score the update against the audit bank, inspect all six components, then apply or override. |
| 9 | Predictive immunization | Manufacture vaccine rows from predicted futures; rehearse every attack to measure poison resistance. |
| 10 | Quarantine and analysis | Dissect held updates, read the findings, release anything honest, rescore against a newer bank. |
| 11 | Secure edge retraining | Retrain on the safe pool plus vaccines; promote only through four gates. |
| 12 | Self-healing | Watch model/twin agreement, roll back to the last trusted model, purge suspect data, rebuild. Healing a model the monitor calls healthy is refused unless you override it. |

---

## Architecture

```
┌───────────────────────────┐
│  Consumer IoT devices     │   STEP 1   6 types, chosen by the operator
│  camera · bulb · plug     │
│  lock · sensor · speaker  │
└─────────────┬─────────────┘
              │  telemetry, on demand only
              ▼
┌───────────────────────────┐
│  Edge gateway             │   STEP 2   everything stays local
└─────────────┬─────────────┘
              ▼
┌───────────────────────────────────────────┐
│  Holographic digital twin layer           │   STEPS 3–4
│  5 planes: resource · network · access    │
│            topology · actuation           │
│  ridge vector-autoregressive forward model│
└─────────────┬─────────────────────────────┘
              ▼
┌───────────────────────────────────────────┐
│  Counterfactual futures (committed)       │   STEP 5
│  "what should happen next?"               │
└─────────────┬─────────────────────────────┘
              │
      ┌───────┴────────┐
      ▼                ▼
 live telemetry   incoming model update
      │                │
      ▼                ▼
┌────────────┐   ┌───────────────────────────┐
│ Threat     │   │ Counterfactual validation │  STEP 8
│ detection  │   │ → Consistency Score (CCS) │
│  STEP 6    │   └───────┬───────────┬───────┘
└─────┬──────┘        SAFE       SUSPICIOUS
      │                 │             │
      │                 ▼             ▼
      │        ┌────────────┐  ┌──────────────┐
      │        │ Safe pool  │  │ Quarantine   │  STEP 10
      │        │  STEP 11   │  │ + analysis   │
      │        └─────┬──────┘  └──────┬───────┘
      │              │                │
      │              ▼                ▼
      │   ┌───────────────────────────────────┐
      │   │ Predictive immunization engine    │  STEP 9
      │   │ AI-generated attack scenarios     │
      │   └───────────────┬───────────────────┘
      │                   ▼
      │   ┌───────────────────────────────────┐
      │   │ Secure retraining + promotion gate│  STEP 11
      │   └───────────────┬───────────────────┘
      │                   ▼
      └──────────►┌───────────────────────────┐
                  │ Trusted threat model      │
                  │ + self-healing rollback   │  STEP 12
                  └───────────────────────────┘
```

---

## The mechanism

### What makes it different

A conventional federated defence asks: *does this contribution look like the
others?* It compares statistics, gradient norms, or distances to a robust mean.
Every one of those questions is about the present and the past, and all of them
are answerable by an attacker who simply stays close to the crowd.

This validator asks: **if I accepted this, what would it do to my ability to
catch tomorrow's attack?**

Concretely, it grafts the update onto a small trusted core, trains a shadow
model, and puts that shadow model in front of the **counterfactual bank** — the
futures the twins committed to *before this update existed*, half of them left
benign and half deformed by each attack class in the taxonomy.

### The Counterfactual Consistency Score

Six components. The first three are counterfactual and future-facing; the last
three examine the update itself, each closing a hole the others leave open.

| Component | Weight | What it asks |
|---|---|---|
| `attack_agreement` | 0.30 | Of the attack-conditioned futures, how many would this update still let us catch? |
| `benign_agreement` | 0.07 | Are benign futures still called benign? (Catches poison that makes the model paranoid.) |
| `stability` | 0.15 | How many verdicts were *downgraded* from attack to normal vs the trusted model? |
| `plane_coherence` | 0.15 | Does each row obey the cross-plane physics of the class it claims to be? |
| `label_integrity` | 0.13 | Has the label mix drifted benign-ward from the trusted prior? |
| `label_agreement` | 0.20 | Do the update's labels agree with the trusted model's reading of its own rows? |

The accept threshold is **not a hand-picked constant**. It is calibrated at
runtime from the empirical CCS distribution of honest updates on your fleet:
`threshold = mean(honest) − z · spread`, floored and clipped. The gate adapts to
the network instead of the network having to suit the gate.

### Why six and not one

Each strategy is caught by a different component, which is precisely why the
combination is needed:

* **Label flipping** collapses `label_integrity` and `attack_agreement`.
* **Clean-label poisoning** leaves labels entirely honest — `label_shift` stays
  under 0.10, so every distributional check waves it through. Only
  `label_agreement` sees it.
* **Backdoor triggers** barely dent accuracy by design; they are caught by the
  trigger-concentration signal and by `plane_coherence`.
* **Gradual poisoning** is individually unremarkable; it erodes source
  reputation and shows up as a modest but real shift.
* **Sybil floods** split the payload below the size worth auditing; a burst of
  never-before-seen sources tightens the gate.

---

## Measured results

On a mixed eight-device fleet (2 cameras, 2 bulbs, plug, lock, sensor, speaker),
seed 1337, reproducible via `python cli.py --walk` on the versions pinned in
`requirements.txt`. The walk exits non-zero if any decision comes out wrong, so
it doubles as an end-to-end check:

**Detection (Step 6)**

| Metric | Value |
|---|---|
| Accuracy | 0.957 |
| Macro F1 | 0.956 |
| False positive rate | 0.049 |
| False negative rate | 0.031 |

**Twin consistency (Step 5)** — normal traffic never falls below the 0.35 flag
threshold; attacks at full intensity are flagged ~92% of the time.

**Poison resistance (Step 9)** — 0.9736 overall, weakest against backdoor and
clean-label poisoning at 0.9528 each. **Promotion (Step 11)** — all four gates
passed, model v2 promoted.

**Live devices (Step 0 / Step 6)** — three real USB peripherals on the
development laptop, 40 paced samples in 11.8 s:

| Metric | Live | Simulated |
|---|---|---|
| Accuracy | 0.9962 | 0.9565 |
| Macro F1 | 0.9961 | 0.9564 |
| False positive rate | 0.0000 | 0.0488 |
| False negative rate | 0.0029 | 0.0307 |

The live figures are higher because the problem is easier, not because the
model is better — see *One number worth reading carefully* above.

**Counterfactual validation (Step 8)** — calibrated threshold **0.8568**,
from an honest mean of 0.9168 with a spread of 0.0068, against 187 bank
scenarios:

| Crafted as | CCS | Gate | Decision | Attributed as |
|---|---|---|---|---|
| honest contribution | 0.910 | 0.857 | ACCEPTED | clean |
| label flipping | 0.629 | 0.857 | QUARANTINED | label_flip |
| gradual poisoning | 0.801 | 0.857 | QUARANTINED | gradual_poisoning |
| backdoor trigger | 0.659 | 0.857 | QUARANTINED | backdoor |
| sybil flood (8 shards) | 0.677–0.730 | 0.857 / 0.907 | QUARANTINED | sybil |
| clean-label poisoning | 0.735 | 0.907 | QUARANTINED | clean_label |

The gate is 0.907 rather than 0.857 for most of the sybil shards and for the
contribution that follows them: a burst of never-before-seen sources adds a
0.05 novelty penalty, which is the one structural signal a sybil flood cannot
hide, since inventing identities is its whole method. It tightens the gate; it
never decides on its own.

**13/13 correct decisions.** No honest update was rejected, and no poisoning
strategy got through.

---

## Step explanations

Every step panel says what it is *about* to do. After you run it, the console
also shows a **"What just happened"** card generated from the numbers that step
actually produced.

Each card carries four things:

* **A headline** stating the outcome — *"Quarantined at CCS 0.612 (gate 0.853)"*,
  not "validation complete".
* **What happened**, in bullets that quote real values: which class the detector
  is weakest on, which CCS component drove the decision, how far the twin
  consistency fell on the devices actually under attack.
* **The key readings**, each with a plain-English note on what that number means
  and, where relevant, a verdict chip (`enough` / `below gate` / `pass`).
* **Why it matters**, then **Next** — with a button that jumps to the step it
  points at.

The colour is the outcome, not the event: green means all clear, amber means
something hostile was caught and handled, red means the system got it wrong.

The text is produced server-side in [`cihdt/explain.py`](cihdt/explain.py), so
the browser console and the terminal front end tell the same story from the same
source. In the terminal it prints after each step:

```bash
python cli.py --walk
```

Use `python cli.py --no-explain` to suppress it, or press `x` in the interactive
CLI to toggle it.

The one rule the module follows: **every sentence must be derived from the
result.** Nothing in it is boilerplate, because a generic explanation teaches
nobody anything they could not have guessed — and the interesting cases are
exactly the ones where the numbers came out badly.

---

## Project structure

```
cihdt/
  config.py            every tunable constant, in one place
  schemas.py           features, holographic planes, threat taxonomy, records
  pipeline.py          ★ the manual step machine — 12 gated operator actions
  simulator/
    profiles.py        per-device baselines and per-attack deformations
    device.py          one simulated device
    fleet.py           the fleet + labelled corpus generator
  twin/
    predictor.py       ridge vector-autoregression with residual roll-out
    twin.py            the holographic twin: planes, futures, consistency
    registry.py        one twin per device
  detection/
    features.py        log compression, cross-plane ratios, device one-hot
    model.py           the edge threat detector
  counterfactual/
    bank.py            ★ the counterfactual audit bank
    validator.py       ★ the CCS, the gate, and strategy attribution
  poisoning/attacks.py five poisoning strategies
  quarantine/store.py  hold, analyse, release, rescore
  immunization/engine.py  vaccines + poison-resistance rehearsal
  retraining/
    registry.py        versioned model store with rollback
    retrainer.py       safe pool, provenance, promotion gates
  selfheal/monitor.py  model/twin agreement, degradation, healing
  live/
    usb.py             real USB peripherals, via Windows PnP
    host.py            ★ the sixteen features from a real machine, with the
                       provenance of every one of them
    device.py          a live device, interchangeable with a simulated one
  server/
    db.py              ★ SQLite: schema, migrations, audit trail
    auth.py            ★ accounts, sessions, password hashing
    api.py             one JSON endpoint per operator action
    pages.py           ★ the console: one page per step, no JavaScript
    html.py            HTML primitives (no template engine, no build step)
  web/styles.css       the whole stylesheet, one file
run.py                 start the console
cli.py                 terminal front end
tests/                 60 tests
```

---

## Configuration

Everything tunable lives in [`cihdt/config.py`](cihdt/config.py) — twin window
and horizon, CCS weights and calibration, detector hyperparameters, promotion
gate limits, self-healing thresholds. No algorithm file hides a magic number.

```bash
CIHDT_SEED=42 python run.py     # different seed
```

---

## Presenting this to faculty

The honest framing, which is also the strongest one:

> We are not claiming that digital twins, AI threat detection, or poisoning
> defence are individually new. **Our novelty is the security decision
> mechanism.** Instead of checking whether an update looks malicious in the
> current state, our framework tests it against multiple predicted
> counterfactual futures generated by the holographic twin — futures committed
> before the update existed. We then use simulated poisoning scenarios to
> proactively retrain and immunize the edge model before real poisoning attacks
> affect the network.

Four things worth demonstrating live:

0. **Step 0 with a USB device plugged in** — scan the bus, enrol the webcam,
   and run the same twelve steps on it. Then open the provenance table and
   explain, before anyone asks, which of the sixteen features are measured from
   the device, which from its host, and which two cannot be obtained at all.


1. **Step 5** — generate futures, then take one tick. The futures were committed
   before that observation existed. Launch an attack in Step 6 and repeat: the
   consistency collapses from ~0.8 to ~0.001, and the anomalous plane names the
   attack type.
2. **Step 8 with clean-label poisoning** — its label shift is under 0.10, so
   every distributional defence accepts it. Show `label_agreement` at ~0.25 and
   the CCS at 0.708 against a 0.856 gate.
3. **Step 11 with a backdoor in the pool** — accuracy still looks excellent. The
   poison-resistance gate is what stops it.

### Known limitations

Stated plainly, because they are the questions a good examiner will ask:

* In simulated mode the fleet is generated from behavioural profiles, not
  captured from real hardware. The profiles are physically motivated but they
  are not a packet capture.
* In live mode the devices are real, but a USB peripheral has no network stack,
  so the network planes are measured on its host and attributed to it. Two of
  the sixteen features cannot be obtained at all on an unprivileged Windows
  host and are reported as missing. Attack rows are synthesised on top of
  measured normal, because real labelled attacks against a webcam do not exist.
* `label_agreement` trusts the incumbent model, so an update carrying a
  genuinely novel attack pattern would be penalised by that term. It is one of
  six for exactly this reason — the counterfactual terms exist to judge damage
  the incumbent cannot see.
* Strategy attribution is rule-based, not learned. A learned attributor would
  need labelled poison to train on, and if we had that we would not need the
  defence. The console shows all five scores so the operator can disagree.
* Poison resistance is measured against the five rehearsed strategies. An
  attacker using a sixth is out of scope for that particular number.
