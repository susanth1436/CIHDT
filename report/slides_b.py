"""Review-2 deck, slides 7-11: gaps, objectives, architecture, FRs, modules."""
from __future__ import annotations

from pptx.enum.text import PP_ALIGN

from build_review2 import (AMBER, CARD, CARD2, INK, NAVY, RED, RULE, SLATE,
                           TEAL, WHITE, bar, box, chip, frame, grid_table,
                           rich, takeaway, tb, write)


# ===========================================================================
# SLIDE 7 - research gap
# ===========================================================================
def slide_gap(prs):
    s = frame(prs, 5, "Gap Analysis", "Research Gap",
              "Six gaps distilled from the survey, each bound to a mechanism "
              "in the proposed framework", 7)

    gaps = [
        ("G1", "Present-State Validation Only",
         "Trust scores, reputation and robust aggregation compare an update "
         "with current or historical observations. None test it against "
         "where the device is expected to be next.",
         "Score against 20 futures committed in advance"),
        ("G2", "Counterfactuals Unused For Security",
         "Counterfactual reasoning is applied to anomaly explanation and "
         "digital twins to monitoring. The two have not been combined into "
         "a decision mechanism.",
         "Audit bank: benign + attack-conditioned futures"),
        ("G3", "Simulation Never Closes The Loop",
         "Attack simulation ends at measuring a detector. It is not fed back "
         "into retraining to manufacture resistance before an attack occurs.",
         "Vaccine synthesis folded into every retrain"),
        ("G4", "Clean-Label Poison Passes Everything",
         "Abnormal-sample identification, data filtering and label-"
         "distribution checks all assume a label was altered. Honest-label "
         "poisoning defeats the entire family.",
         "Label agreement against the trusted incumbent"),
        ("G5", "The Twin Is Itself A Target",
         "If hostile telemetry enters the twin's history, the twin's notion "
         "of normal moves toward the attack — beating the defence before "
         "the classifier runs.",
         "Trust gate: flagged observations refused entry"),
        ("G6", "Recovery Is Manual And Total",
         "Once a model is poisoned, restoring it and purging contaminated "
         "data is an operator task, and the usual remedy is discarding the "
         "whole pool.",
         "Provenance-tracked purge + versioned rollback"),
    ]
    for i, (tag, head, body, fix) in enumerate(gaps):
        col, row = i % 3, i // 3
        x = 0.73 + col * 4.14
        y = 1.72 + row * 2.34
        box(s, x, y, 3.86, 2.16, fill=WHITE, border=RULE)
        chip(s, x + 0.16, y + 0.14, 0.62, tag, color=WHITE, fill=NAVY,
             size=11.5, h=0.26)
        t = tb(s, x + 0.90, y + 0.11, 2.84, 0.36)
        write(t, head, size=14, bold=True, color=NAVY, line=0.95)
        t = tb(s, x + 0.16, y + 0.56, 3.56, 0.94)
        write(t, body, size=12, color=SLATE, line=1.08)
        box(s, x + 0.16, y + 1.54, 3.56, 0.48, fill=CARD, border=None)
        t = tb(s, x + 0.30, y + 1.62, 3.30, 0.36)
        rich(t, [("→  ", {"size": 12.5, "bold": True, "color": TEAL}),
                 (fix, {"size": 12.5, "bold": True, "color": NAVY})],
             line=1.0)

    takeaway(s, "The strongest single gap:",
             "no existing work validates a retraining update against multiple "
             "plausible future states committed in advance, and none closes "
             "simulated attacks back into the retraining loop.")


# ===========================================================================
# SLIDE 8 - objectives
# ===========================================================================
def slide_objectives(prs):
    s = frame(prs, 6, "Research Scope", "Objectives",
              "Seven objectives, each mapped one-to-one onto an identified "
              "gap and a measurable criterion", 8)

    rows = [
        ["#", "Objective", "Gap", "Measurable Criterion", "Deliverable",
         "Status"],
        ["O1", "Simulate a heterogeneous consumer IoT fleet and an on-demand "
               "edge gateway.", "G5",
         "Six device types separable on baseline behaviour",
         "Device simulator + gateway", ("Complete", TEAL)],
        ["O2", "Build a holographic twin per device across five behavioural "
               "planes.", "G5",
         "Zero false flags on healthy traffic",
         "Twin registry + plane scoring", ("Complete", TEAL)],
        ["O3", "Commit counterfactual futures before the observation they "
               "judge exists.", "G1",
         "20 futures x 5-tick horizon, committed pre-hoc",
         "Ridge VAR forward model", ("Complete", TEAL)],
        ["O4", "Design a Counterfactual Consistency Score that gates every "
               "retraining update.", "G2",
         "Separation between honest and poisoned CCS",
         "Six-component validator", ("Complete", TEAL)],
        ["O5", "Detect clean-label poisoning that carries no label shift "
               "at all.", "G4",
         "Quarantined at label shift below 0.10",
         "Label-agreement component", ("Complete", TEAL)],
        ["O6", "Immunize the model against synthesised poisoning before real "
               "attacks.", "G3",
         "Poison resistance against five strategies",
         "Immunization engine", ("Complete", TEAL)],
        ["O7", "Benchmark against reactive baselines across poisoning "
               "rates.", "G1",
         "Attack success rate vs anomaly / robust-aggregation baselines",
         "Comparative harness", ("In progress", AMBER)],
    ]
    grid_table(s, 0.69, 1.62, 11.95, rows,
               [0.50, 3.45, 0.52, 3.05, 2.55, 1.20],
               header_h=0.34, row_h=0.44, head_size=11.5, body_size=10.5)

    panels = [
        ("SUSTAINABLE DEVELOPMENT GOALS",
         [("SDG 9", "Industry, Innovation & Infrastructure — resilient "
                    "connected-device infrastructure."),
          ("SDG 11", "Sustainable Cities & Communities — securing the "
                     "smart-home sensing layer.")]),
        ("OUTCOME CLASSIFICATION",
         [("Primary", "Patent on the counterfactual validation mechanism."),
          ("Secondary", "Conference paper, Scopus-indexed.")]),
        ("TECHNOLOGY READINESS LEVEL",
         [("TRL 4", "Technology validated in a laboratory environment."),
          ("Basis", "Measured in simulation; no hardware deployment yet.")]),
    ]
    for i, (head, items) in enumerate(panels):
        x = 0.71 + i * 4.14
        box(s, x, 5.12, 3.86, 1.22, fill=CARD, border=RULE)
        t = tb(s, x + 0.16, 5.20, 3.54, 0.22)
        write(t, head, size=11.5, bold=True, color=TEAL)
        for j, (k, v) in enumerate(items):
            t = tb(s, x + 0.16, 5.46 + j * 0.42, 3.54, 0.40)
            rich(t, [(k + "  ", {"size": 12, "bold": True, "color": NAVY}),
                     (v, {"size": 12, "color": SLATE})], line=1.02)

    takeaway(s, "Confirm with guide:",
             "the SDG mapping, outcome classification and the TRL 4 claim are "
             "proposed rather than agreed. TRL 5 would require deployment on "
             "physical gateway hardware.")


# ===========================================================================
# SLIDE 9 - architecture
# ===========================================================================
def slide_architecture(prs):
    s = frame(prs, 7, "System Design",
              "Framework / Architecture / Block Diagram",
              "Closed-loop edge architecture  ·  every stage is an "
              "explicit operator action, nothing runs autonomously", 9)

    # ---- device plane -----------------------------------------------------
    box(s, 0.69, 1.64, 2.20, 4.28, fill=WHITE, border=RULE)
    t = tb(s, 0.82, 1.76, 1.96, 0.22)
    write(t, "DEVICE PLANE", size=12, bold=True, color=TEAL)
    devices = ["Smart Camera", "Smart Bulb", "Smart Plug", "Smart Lock",
               "Temperature Sensor", "Smart Speaker"]
    for i, d in enumerate(devices):
        box(s, 0.82, 2.06 + i * 0.42, 1.96, 0.34, fill=CARD, border=None)
        t = tb(s, 0.94, 2.13 + i * 0.42, 1.80, 0.24)
        write(t, d, size=11.5, color=NAVY)
    t = tb(s, 0.82, 4.66, 1.96, 0.20)
    write(t, "16 telemetry features", size=11, bold=True, color=SLATE)
    t = tb(s, 0.82, 4.90, 1.96, 0.92)
    write(t, "CPU · memory · traffic · packet rate · connections · "
             "failed logins · ports · entropy · power",
          size=10.5, color=SLATE, line=1.06)

    t = tb(s, 2.94, 3.60, 0.62, 0.22, align=PP_ALIGN.CENTER)
    write(t, "telemetry", size=10, color=SLATE)
    t = tb(s, 2.94, 3.80, 0.62, 0.22, align=PP_ALIGN.CENTER)
    write(t, "▶", size=13, color=TEAL)

    # ---- edge gateway -----------------------------------------------------
    box(s, 3.62, 1.64, 4.92, 4.28, fill=WHITE, border=RULE)
    bar(s, 3.62, 1.64, 4.92, 0.045, TEAL)
    t = tb(s, 3.76, 1.78, 4.64, 0.22)
    write(t, "EDGE GATEWAY  ·  ALL PROCESSING LOCAL", size=12,
          bold=True, color=TEAL)

    modules = [
        ("M1", "Telemetry Collector",
         "on-demand ticks; nothing is collected autonomously"),
        ("M2", "Holographic Twin Layer",
         "five planes; refuses hostile observations into history"),
        ("M3", "Counterfactual Future Bank",
         "20 futures x 5 ticks, benign + attack-conditioned"),
        ("M4", "Threat Detector",
         "random forest over 30 engineered features, 7 classes"),
        ("M5", "CCS Validation Gate",
         "six components; threshold calibrated on honest traffic"),
    ]
    for i, (tag, head, sub) in enumerate(modules):
        y = 2.08 + i * 0.74
        box(s, 3.76, y, 4.64, 0.62, fill=CARD, border=RULE)
        chip(s, 3.88, y + 0.08, 0.40, tag, color=WHITE, fill=NAVY, size=10,
             h=0.22)
        t = tb(s, 4.38, y + 0.06, 3.94, 0.24)
        write(t, head, size=13, bold=True, color=NAVY)
        t = tb(s, 4.38, y + 0.30, 3.94, 0.26)
        write(t, sub, size=10.5, color=SLATE)
        if i < len(modules) - 1:
            t = tb(s, 6.00, y + 0.62, 0.30, 0.14, align=PP_ALIGN.CENTER)
            write(t, "▼", size=9, color=TEAL)

    t = tb(s, 3.76, 5.72, 4.64, 0.22, align=PP_ALIGN.CENTER)
    write(t, "No cloud dependency — the update channel is never trusted",
          size=10.5, italic=True, color=SLATE)

    # ---- decision fork ----------------------------------------------------
    t = tb(s, 8.58, 3.60, 0.62, 0.22, align=PP_ALIGN.CENTER)
    write(t, "verdict", size=10, color=SLATE)
    t = tb(s, 8.58, 3.80, 0.62, 0.22, align=PP_ALIGN.CENTER)
    write(t, "▶", size=13, color=TEAL)

    box(s, 9.26, 1.64, 3.38, 4.28, fill=WHITE, border=RULE)
    t = tb(s, 9.40, 1.78, 3.10, 0.22)
    write(t, "DECISION & RECOVERY", size=12, bold=True, color=TEAL)

    box(s, 9.40, 2.08, 1.48, 0.56, fill=CARD, border=RULE)
    t = tb(s, 9.40, 2.16, 1.48, 0.22, align=PP_ALIGN.CENTER)
    write(t, "SAFE", size=11.5, bold=True, color=TEAL)
    t = tb(s, 9.40, 2.38, 1.48, 0.22, align=PP_ALIGN.CENTER)
    write(t, "safe pool", size=10.5, color=SLATE)

    box(s, 11.02, 2.08, 1.48, 0.56, fill=CARD, border=RULE)
    t = tb(s, 11.02, 2.16, 1.48, 0.22, align=PP_ALIGN.CENTER)
    write(t, "SUSPICIOUS", size=11.5, bold=True, color=RED)
    t = tb(s, 11.02, 2.38, 1.48, 0.22, align=PP_ALIGN.CENTER)
    write(t, "quarantine", size=10.5, color=SLATE)

    lower = [
        ("M6", "Predictive Immunization",
         "vaccines synthesised from committed futures"),
        ("M7", "Secure Retraining",
         "four promotion gates; candidate discarded on failure"),
        ("M8", "Self-Healing Controller",
         "rollback to last trusted model, purge by provenance"),
    ]
    for i, (tag, head, sub) in enumerate(lower):
        y = 2.84 + i * 0.78
        box(s, 9.40, y, 3.10, 0.66, fill=CARD, border=RULE)
        chip(s, 9.52, y + 0.09, 0.40, tag, color=WHITE, fill=NAVY, size=10,
             h=0.22)
        t = tb(s, 10.02, y + 0.07, 2.38, 0.24)
        write(t, head, size=12.5, bold=True, color=NAVY)
        t = tb(s, 10.02, y + 0.31, 2.38, 0.30)
        write(t, sub, size=10.5, color=SLATE, line=1.0)

    box(s, 9.40, 5.20, 3.10, 0.56, fill=NAVY, border=None)
    t = tb(s, 9.52, 5.28, 2.86, 0.42, align=PP_ALIGN.CENTER)
    write(t, "Trusted model returned to M4", size=11.5, bold=True,
          color=WHITE, line=1.0)

    takeaway(s, "Closed loop:",
             "the retrained model feeds back into detection, and the twins' "
             "futures feed forward into the next validation — so the "
             "defence improves from its own operation rather than from an "
             "external attack feed.")


# ===========================================================================
# SLIDE 10 - functional requirements
# ===========================================================================
def slide_frs(prs):
    s = frame(prs, 8, "Specification", "Functional Requirements",
              "System-level requirements expressed as verifiable "
              "shall-statements", 11)

    frs = [
        ("FR-01", "Device Simulation",
         "The system shall generate continuous 16-feature telemetry for six "
         "consumer device types with distinct behavioural baselines."),
        ("FR-02", "On-Demand Ingestion",
         "The gateway shall collect, timestamp and buffer telemetry only when "
         "an operator requests a tick; no collection shall occur autonomously."),
        ("FR-03", "Twin Synchronisation",
         "Each device shall have a twin whose five-plane state is updated from "
         "trusted telemetry, and which refuses observations judged hostile."),
        ("FR-04", "Future Commitment",
         "Each ready twin shall commit 20 predicted trajectories over a "
         "five-tick horizon before the observation they will judge exists."),
        ("FR-05", "Threat Detection",
         "The system shall classify normal traffic and six attack classes, "
         "returning a class, confidence and operator-facing risk level."),
        ("FR-06", "Counterfactual Validation",
         "Every retraining update shall be scored on six components against "
         "the audit bank and judged on a calibrated threshold."),
        ("FR-07", "Operator Override",
         "The system shall apply an accept or quarantine decision only on "
         "explicit instruction, and shall record any override."),
        ("FR-08", "Quarantine Ledger",
         "Held updates shall be retained intact with update ID, source, "
         "suspected strategy, score and timestamp, and shall be re-scorable."),
        ("FR-09", "Predictive Immunization",
         "The system shall synthesise vaccine rows from committed futures and "
         "measure poison resistance against five rehearsed strategies."),
        ("FR-10", "Guarded Promotion & Rollback",
         "A candidate model shall replace the incumbent only if all four gates "
         "pass; otherwise the incumbent is retained and can be rolled back."),
    ]
    for i, (tag, head, body) in enumerate(frs):
        col, row = i % 2, i // 2
        x = 0.69 + col * 6.13
        y = 1.62 + row * 0.94
        box(s, x, y, 5.82, 0.84, fill=WHITE, border=RULE)
        chip(s, x + 0.14, y + 0.11, 0.66, tag, color=WHITE, fill=TEAL,
             size=10, h=0.22)
        t = tb(s, x + 0.90, y + 0.09, 4.80, 0.24)
        write(t, head, size=12.5, bold=True, color=NAVY)
        t = tb(s, x + 0.90, y + 0.33, 4.80, 0.46)
        write(t, body, size=11.5, color=SLATE, line=1.05)

    takeaway(s, "Verification:",
             "FR-01 to FR-10 are each covered by automated tests; the suite "
             "contains 64 tests, including one asserting that no stage "
             "advances the fleet without an explicit request.")


# ===========================================================================
# SLIDE 11 - modules
# ===========================================================================
def slide_modules(prs):
    s = frame(prs, 9, "Decomposition", "Modules",
              "Ten modules, their responsibilities and the technology each "
              "actually uses", 12)

    rows = [
        ["Module", "Responsibility", "Input", "Output", "Key Technology",
         "Status"],
        ["M1  Device Simulator",
         "Emit per-device telemetry with baseline drift and attack "
         "deformation.", "Operator tick", "16-feature records",
         "NumPy profile models", ("Complete", TEAL)],
        ["M2  Edge Gateway",
         "Receive, buffer and route telemetry; expose one endpoint per "
         "action.", "Telemetry batches", "Buffered observations",
         "FastAPI, in-memory state", ("Complete", TEAL)],
        ["M3  Holographic Twin",
         "Maintain five-plane state and gate hostile data out of history.",
         "Trusted observations", "Per-plane deviation",
         "EWMA + plane projections", ("Complete", TEAL)],
        ["M4  Future Generator",
         "Fit a forward model and roll out committed trajectories.",
         "Twin history", "20 x 5 futures",
         "Ridge vector autoregression", ("Complete", TEAL)],
        ["M5  Threat Detector",
         "Classify an observation into normal or one of six attack classes.",
         "Engineered features", "Class, confidence, risk",
         "scikit-learn random forest", ("Complete", TEAL)],
        ["M6  Poisoning Forge",
         "Craft label-flip, gradual, backdoor, Sybil and clean-label "
         "updates.", "Held-out pool", "Model updates",
         "Five strategy generators", ("Complete", TEAL)],
        ["M7  CCS Validator",
         "Train a shadow model and score it against the audit bank.",
         "Update + bank + core", "Six components, verdict",
         "Shadow forest + calibration", ("Complete", TEAL)],
        ["M8  Quarantine Zone",
         "Hold suspect updates intact, run forensics, re-score on demand.",
         "Quarantined updates", "Findings, release decision",
         "Provenance ledger", ("Complete", TEAL)],
        ["M9  Immunization Engine",
         "Synthesise vaccines and rehearse every poisoning strategy.",
         "Committed futures", "Vaccine rows, resistance",
         "Boundary / relabel / trigger", ("Complete", TEAL)],
        ["M10  Console & Self-Heal",
         "Drive all twelve steps manually; roll back and purge on "
         "degradation.", "Operator actions", "State, explanations",
         "Server-rendered UI, model registry", ("Complete", TEAL)],
    ]
    grid_table(s, 0.69, 1.62, 11.95, rows,
               [2.10, 3.20, 1.72, 1.85, 2.05, 1.10],
               header_h=0.34, row_h=0.44, head_size=11.5, body_size=10)

    takeaway(s, "Corrected since Review-1:",
             "the forward model is ridge VAR rather than LSTM/GRU, transport "
             "is HTTP rather than MQTT, and the console is server-rendered "
             "HTML with no JavaScript — "
             "each chosen so the whole pipeline runs on a laptop-class "
             "gateway with no GPU.")
