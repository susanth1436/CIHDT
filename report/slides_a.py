"""Review-2 deck, slides 1-8."""
from __future__ import annotations

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from build_review2 import (AMBER, CARD, INK, NAVY, RED, RULE, SLATE, TEAL,
                           TOTAL_SLIDES, W, WHITE, DATE, bar, box, chip,
                           frame, grid_table, new_slide, rich, takeaway, tb,
                           write, footer)


# ===========================================================================
# SLIDE 1 - title
# ===========================================================================
def slide_title(prs):
    s = new_slide(prs)
    bar(s, 0.0, 0.0, W, 0.10, INK)

    t = tb(s, 0.55, 0.78, 12.23, 0.30)
    write(t, "B.TECH  ·  BCSE497J — PROJECT-I  ·  "
             "FALL SEMESTER 2026", size=15, bold=True, color=SLATE)
    t = tb(s, 0.55, 1.11, 12.23, 0.30)
    write(t, "MAJOR PROJECT REVIEW-2", size=14, bold=True, color=TEAL)

    t = tb(s, 1.10, 1.55, 11.13, 1.64)
    write(t, "Counterfactual Immunization of Holographic Digital Twins",
          size=28, bold=True, color=INK, line=1.12)
    write(t, "Predictive Edge-AI Retraining for Real-Time Threat Detection "
             "in Consumer IoT Networks",
          size=28, bold=True, color=INK, para=1, line=1.12)

    t = tb(s, 1.10, 3.24, 11.13, 0.40)
    write(t, "A Proactive, Self-Healing Defence Against Model Poisoning "
             "at the Edge", size=19, color=SLATE)

    pillars = ["HOLOGRAPHIC TWINS", "COUNTERFACTUAL FUTURES",
               "CCS VALIDATION GATE", "PREDICTIVE IMMUNIZATION",
               "SELF-HEALING ROLLBACK"]
    for i, p in enumerate(pillars):
        x = 0.69 + i * 2.42
        bar(s, x, 3.74, 2.28, 0.025, TEAL)
        t = tb(s, x, 3.84, 2.28, 0.24)
        write(t, p, size=12, bold=True, color=NAVY)

    # Sorted on register number, as the report template requires.
    t = tb(s, 2.20, 4.46, 3.80, 0.22)
    write(t, "TEAM MEMBERS", size=12.5, bold=True, color=TEAL)
    for i, (name, reg) in enumerate([("ATRIK", "23BAI0136"),
                                     ("T V SAI SUSANTH", "23BCI0231"),
                                     ("PUSHPAK", "23BCT0129")]):
        t = tb(s, 2.20, 4.76 + i * 0.30, 4.20, 0.28)
        rich(t, [(name, {"size": 14.5, "bold": True, "color": NAVY}),
                 ("     " + reg, {"size": 14.5, "color": SLATE})])

    t = tb(s, 7.60, 4.46, 3.80, 0.22)
    write(t, "FACULTY GUIDE", size=12.5, bold=True, color=TEAL)
    t = tb(s, 7.60, 4.76, 4.20, 0.28)
    write(t, "Mr. Jim Solomon Raja", size=15.5, bold=True, color=NAVY)
    t = tb(s, 7.60, 5.08, 4.60, 0.28)
    write(t, "Employee ID 22533  ·  SCOPE", size=13, color=SLATE)

    bar(s, 0.55, 5.70, 12.23, 0.012, RULE)
    t = tb(s, 0.55, 5.84, 12.23, 0.30)
    write(t, "School of Computer Science and Engineering (SCOPE)  ·  "
             "Vellore Institute of Technology", size=15, bold=True, color=NAVY)

    box(s, 1.30, 6.24, 10.73, 0.54, fill=CARD, border=RULE)
    bar(s, 1.30, 6.24, 0.05, 0.54, TEAL)
    t = tb(s, 1.52, 6.36, 10.35, 0.40)
    rich(t, [("Review-2 scope:  ", {"size": 13.5, "bold": True,
                                    "color": TEAL}),
             ("all twelve pipeline stages are implemented and measured on a "
              "simulated eight-device fleet; comparative baselines and the "
              "poisoning-rate sweep remain outstanding.",
              {"size": 13.5, "color": NAVY})], line=1.02)

    t = tb(s, 0.55, 7.06, 2.0, 0.22)
    write(t, DATE, size=12.5, color=SLATE)
    t = tb(s, 5.20, 7.06, 2.90, 0.22, align=PP_ALIGN.CENTER)
    write(t, "SCOPE  ·  VIT", size=12.5, color=SLATE)
    t = tb(s, 10.78, 7.06, 2.0, 0.22, align=PP_ALIGN.RIGHT)
    write(t, f"1 / {TOTAL_SLIDES}", size=12.5, color=SLATE)


# ===========================================================================
# SLIDE 2 - compliance
# ===========================================================================
def slide_compliance(prs):
    s = frame(prs, 1, "Compliance", "Approval Mail From Guide",
              "Guide sign-off on the five Review-2 checkpoints, obtained by "
              "e-mail", 2)

    box(s, 0.69, 1.68, 5.60, 4.48, fill=WHITE, border=RULE)
    t = tb(s, 0.90, 1.84, 5.20, 0.24)
    write(t, "APPROVAL CHECKPOINTS", size=13, bold=True, color=TEAL)

    checks = [("1.  Meeting with guide frequently", "SATISFIED", TEAL),
              ("2.  PowerPoint presentation", "APPROVED", TEAL),
              ("3.  Project demonstration", "APPROVED", TEAL),
              ("4.  Project report draft", "SATISFIED", TEAL),
              ("5.  Project outcome", "ONGOING", AMBER)]
    for i, (label, status, colour) in enumerate(checks):
        y = 2.24 + i * 0.74
        box(s, 0.90, y, 5.18, 0.58, fill=CARD, border=RULE)
        bar(s, 0.90, y, 0.045, 0.58, colour)
        t = tb(s, 1.12, y + 0.16, 3.30, 0.28)
        write(t, label, size=14.5, bold=True, color=NAVY)
        chip(s, 4.46, y + 0.17, 1.46, status, color=colour, fill=WHITE)

    box(s, 6.70, 1.68, 5.94, 4.48, fill=WHITE, border=RULE)
    t = tb(s, 6.95, 1.88, 5.50, 0.30)
    rich(t, [("Template deadline for guide approval:  ",
              {"size": 13.5, "color": SLATE}),
             ("01-09-2026", {"size": 13.5, "bold": True, "color": NAVY})])

    box(s, 6.95, 2.32, 5.44, 1.94, fill=CARD, border=RULE)
    t = tb(s, 7.15, 3.02, 5.04, 0.66, align=PP_ALIGN.CENTER)
    write(t, "PASTE THE GUIDE'S APPROVAL", size=15.5, bold=True, color=SLATE)
    write(t, "E-MAIL SCREENSHOT HERE", size=15.5, bold=True, color=SLATE,
          para=1)

    t = tb(s, 6.95, 4.42, 5.44, 1.10)
    write(t, "The mail must state that the Fall Semester Project Review-2 for "
             "this project ID has been approved, followed by the five "
             "checkpoints listed opposite.", size=13.5, color=SLATE, line=1.15)

    takeaway(s, "Status:",
             "Approval has been obtained; the mail is supplied alongside the "
             "deck. Paste the screenshot opposite so the panel can see it "
             "in-slide.")


# ===========================================================================
# SLIDE 3 - aim
# ===========================================================================
def slide_aim(prs):
    s = frame(prs, 2, "Overview", "Aim",
              "Carried forward from Review-1, with the decision mechanism "
              "stated precisely", 3)

    t = tb(s, 0.75, 1.62, 4.00, 0.22)
    write(t, "PRIMARY RESEARCH AIM", size=12.5, bold=True, color=TEAL)
    box(s, 0.73, 1.84, 11.87, 1.28, fill=CARD, border=RULE)
    bar(s, 0.73, 1.84, 0.05, 1.28, TEAL)
    t = tb(s, 0.98, 1.96, 11.48, 1.12)
    write(t, "“To design and empirically validate a proactive, "
             "self-immunizing defence for edge-AI threat detection in "
             "consumer IoT networks, in which a holographic digital twin of "
             "every device commits to counterfactual future states in "
             "advance, every retraining update is validated against those "
             "committed futures before it is accepted, and the detection "
             "model is immunized against generated poisoning strategies "
             "before real attacks occur.”",
          size=14.5, color=NAVY, line=1.13)

    pillars = [
        ("01", "Holographic Twinning",
         "Model each device as five partial projections — resource, "
         "network, access, topology, actuation — so a single-plane "
         "attack cannot be averaged into invisibility."),
        ("02", "Counterfactual Futures",
         "Commit 20 predicted trajectories per device, five ticks ahead, "
         "before the observation they will judge exists."),
        ("03", "Pre-Acceptance Validation",
         "Score every retraining update on a six-component Counterfactual "
         "Consistency Score and quarantine it before it touches the model."),
        ("04", "Predictive Immunization",
         "Synthesise vaccine rows from the twins' own committed futures and "
         "fold them into retraining ahead of any real attack."),
        ("05", "Guarded Promotion",
         "Install a retrained model only if accuracy, poison resistance, "
         "false-positive rate and pool size all clear their gates."),
        ("06", "Self-Healing Rollback",
         "On sustained degradation, revert to the last trusted model and "
         "purge the hostile contributor's rows by provenance."),
    ]
    for i, (num, head, body) in enumerate(pillars):
        col, row = i % 3, i // 3
        x = 0.73 + col * 4.14
        y = 3.22 + row * 1.56
        box(s, x, y, 3.86, 1.44, fill=WHITE, border=RULE)
        chip(s, x + 0.16, y + 0.15, 0.42, num, color=WHITE, fill=TEAL,
             size=11.5, h=0.26)
        t = tb(s, x + 0.68, y + 0.13, 3.04, 0.30)
        write(t, head, size=15, bold=True, color=NAVY)
        t = tb(s, x + 0.16, y + 0.48, 3.56, 0.90)
        write(t, body, size=12.5, color=SLATE, line=1.06)

    takeaway(s, "Definition note:",
             "“Committed in advance” is load-bearing — the "
             "futures are frozen before the update or observation exists, "
             "which makes the comparison a prediction test rather than a "
             "retrospective fit.")


# ===========================================================================
# SLIDE 4 - abstract
# ===========================================================================
def slide_abstract(prs):
    s = frame(prs, 3, "Abstract", "Abstract",
              "Structured per IEEE convention  ·  status updated to "
              "reflect the implemented system", 4)

    rows = [
        ("1", "Background",
         "Consumer IoT networks — cameras, locks, plugs, bulbs, sensors, "
         "speakers — are increasingly defended by edge-AI models that "
         "retrain continuously on locally collected telemetry."),
        ("2", "Problem",
         "Continuous edge retraining is an open ingestion path. Falsified or "
         "mislabelled contributions can silently blind the detector, and the "
         "damage is discovered only after an attack has already been missed."),
        ("3", "Limitation",
         "Existing defences — anomaly filtering, trust and reputation "
         "scoring, robust aggregation — judge an update after submission "
         "and only against present or past observations. Clean-label "
         "poisoning, whose labels are entirely honest, passes all of them."),
        ("4", "Approach",
         "Each device is mirrored by a holographic twin committing to 20 "
         "counterfactual futures — half benign, half deformed by each "
         "attack class — forming an audit bank. An update is grafted onto "
         "a trusted core, a shadow model trained, and its behaviour on "
         "that bank yields the Counterfactual Consistency Score."),
        ("5", "Status",
         "All twelve stages are implemented and tested. The detector "
         "reaches 95.7% accuracy; the calibrated gate sits at 0.857; "
         "honest updates score 0.91–0.94 against 0.58–0.79 for all five "
         "poisoning strategies — 13 of 13 correct decisions."),
    ]
    y = 1.56
    for num, head, body in rows:
        h = 1.02 if len(body) > 230 else 0.80
        box(s, 0.73, y, 11.87, h, fill=WHITE, border=RULE)
        chip(s, 0.92, y + 0.15, 0.40, num, color=WHITE, fill=NAVY, size=12,
             h=0.26)
        t = tb(s, 1.46, y + 0.13, 1.70, 0.36)
        write(t, head, size=15, bold=True, color=TEAL)
        t = tb(s, 3.16, y + 0.13, 9.28, h - 0.22)
        write(t, body, size=13, color=NAVY, line=1.10)
        y += h + 0.07

    takeaway(s, "Change since Review-1:",
             "Immunization and self-healing are no longer “planned” "
             "— both are implemented and measured, and the forward model "
             "is a ridge vector autoregression rather than an LSTM.")


# ===========================================================================
# SLIDES 5 and 6 - literature review
# ===========================================================================
def slide_lit1(prs):
    s = frame(prs, 4, "Literature Review", "Literature Review  (1 of 2)",
              "Paper  ·  Objective  ·  Methodology  ·  "
              "Pros & Cons  ·  Findings and the gap left open", 5)

    rows = [
        ["Paper", "Objective", "Methodology", "Pros / Cons",
         "Findings & Gap Left"],
        ["[1] Alcaraz & Lopez\nIEEE COMST, 2022",
         "Map the security threats of digital twins across their life cycle.",
         "Systematic survey of DT architectures, synchronisation and attack "
         "surface.",
         "+ Complete threat taxonomy.\n− No runtime defence mechanism "
         "proposed.",
         "The twin is itself a poisoning and spoofing target; trusted state "
         "synchronisation is essential but unaddressed."],
        ["[2] Tian et al.\nACM CSUR, 2022",
         "Survey poisoning attacks and countermeasures across ML pipelines.",
         "Taxonomy of attack surfaces and defence families.",
         "+ Comprehensive coverage.\n− Every defence surveyed is "
         "post-hoc and detection-based.",
         "Robust aggregation and anomaly filtering dominate; proactive "
         "immunization is named as an open gap."],
        ["[3] Yang et al.\nComputers & Security, 2023",
         "Keep federated IoT intrusion detection dependable under poisoning.",
         "Lightweight detection and filtering of malicious client updates.",
         "+ Low edge overhead.\n− Reactive: acts only after the update "
         "is submitted.",
         "Restores accuracy under label-flipping and backdoor clients, but "
         "only once damage is measurable."],
        ["[4] Nguyen et al.\nIEEE ICDCS, 2019",
         "Detect compromised consumer IoT devices without labelled attack "
         "data.",
         "Federated self-learning GRU models of device-type traffic on the "
         "gateway.",
         "+ Label-free and privacy-preserving.\n− Assumes every "
         "participating client is honest.",
         "95.6% detection of Mirai-infected devices in 257 ms — but the "
         "honest-client assumption is exactly what poisoning breaks."],
    ]
    grid_table(s, 0.69, 1.66, 11.95, rows, [1.95, 2.15, 2.35, 2.95, 2.83],
               header_h=0.36, row_h=1.06, head_size=12, body_size=10.5)

    takeaway(s, "Reading across these four:",
             "The threat is well mapped and detection is well solved — "
             "but every defence acts after submission, and each assumes the "
             "twin itself is trustworthy.")


def slide_lit2(prs):
    s = frame(prs, 4, "Literature Review", "Literature Review  (2 of 2)",
              "Continued  ·  the three works that bound our own "
              "mechanism most directly", 6)

    rows = [
        ["Paper", "Objective", "Methodology", "Pros / Cons",
         "Findings & Gap Left"],
        ["[5] Sulem et al.\narXiv:2203.11103, 2022",
         "Explain anomalies in time-series models using counterfactuals.",
         "Model-agnostic generation of diverse counterfactual ensembles.",
         "+ Interpretable and model-agnostic.\n− Used for explanation "
         "only, never as a security decision.",
         "Counterfactual alternatives separate genuine anomalies from benign "
         "variation — but are never used to gate a model update."],
        ["[6] Madry et al.\nICLR, 2018",
         "Build models that resist adversarially crafted inputs.",
         "Min-max adversarial training on generated worst-case perturbations.",
         "+ Measurable, durable robustness gain.\n− Targets test-time "
         "evasion, not training-data poisoning.",
         "Training on generated attacks yields real resistance — the "
         "principle predictive immunization transfers to poisoning."],
        ["[7] Shafahi et al.\nNeurIPS, 2018",
         "Poison a model without altering any label.",
         "Feature-collision optimisation producing clean-label poison.",
         "+ Defeats label-inspection defences entirely.\n− Demonstrated "
         "on vision, not on IoT telemetry.",
         "Honest-label poisoning is practical, which invalidates the "
         "label-distribution checks most IoT defences rely on."],
    ]
    grid_table(s, 0.69, 1.66, 11.95, rows, [1.95, 2.15, 2.35, 2.95, 2.83],
               header_h=0.36, row_h=1.06, head_size=12, body_size=10.5)

    t = tb(s, 0.73, 5.14, 6.00, 0.22)
    write(t, "RESEARCH EVOLUTION IN IOT POISONING DEFENCE", size=12.5,
          bold=True, color=TEAL)
    stages = [
        ("Signature IDS", "Known patterns only; blind to novel vectors."),
        ("Anomaly Filtering", "Statistical outlier rejection on updates."),
        ("Robust Aggregation", "Krum, trimmed mean; bounds influence."),
        ("Trust / Reputation", "Scores a source from its own history."),
        ("This Work", "Validates against committed futures; immunizes first."),
    ]
    for i, (head, body) in enumerate(stages):
        x = 0.73 + i * 2.44
        box(s, x, 5.40, 2.22, 0.86,
            fill=CARD if i < 4 else WHITE,
            border=RULE)
        if i == 4:
            bar(s, x, 5.40, 2.22, 0.045, TEAL)
        t = tb(s, x + 0.12, 5.50, 1.98, 0.24)
        write(t, head, size=13, bold=True, color=NAVY if i < 4 else TEAL)
        t = tb(s, x + 0.12, 5.74, 1.98, 0.46)
        write(t, body, size=11, color=SLATE, line=1.05)
        if i < 4:
            t = tb(s, x + 2.24, 5.72, 0.20, 0.24)
            write(t, "▶", size=12, color=RULE)

    takeaway(s, "Collective conclusion:",
             "Counterfactual reasoning exists for explanation and adversarial "
             "training exists for evasion — neither has been turned into "
             "a pre-acceptance gate on edge retraining.")
