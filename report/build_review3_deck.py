"""Build the Review-3 deck on the faculty template, in the Gamma theme.

    python report/build_review3_deck.py

Slide order, titles and footer furniture come from the supplied template
(Review 3- 28-10- 2026.pptx); the look comes from the reference Gamma deck;
the content comes from the project report.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image                                            # noqa: E402
from pptx import Presentation                                    # noqa: E402
from pptx.dml.color import RGBColor                              # noqa: E402
from pptx.enum.text import PP_ALIGN                              # noqa: E402
from pptx.util import Inches, Pt                                 # noqa: E402

from deck_theme import (ACCENT, BODY, BODY_FONT, BODY_L, BODY_W,  # noqa: E402
                        CARD_H, CARD_L, CARD_T, CARD_W, HEAD_FONT, HEADING,
                        MUTED, OK, SLIDE_H, SLIDE_W, WARN, blank, bullet,
                        callout, footer, heading, line, make_background, run,
                        stat, table, textbox)

FIG = HERE / "figures"
OUT = HERE / "CIHDT_Review3_Deck.pptx"
BG = FIG / "deck_background.png"
ARCH = FIG / "fig_patent_architecture.png"
ARCH_HI = FIG / "fig_patent_architecture_hi.png"

TITLE = ("System and Method for Counterfactual-Driven Adaptive Security "
         "Control and Verified Model Updating in Edge-Deployed Digital "
         "Twins for Consumer Internet of Things Networks")

TEAM = [("ATRIK", "23BAI0136"),
        ("T V SAI SUSANTH", "23BCI0231"),
        ("PUSHPAK", "23BCT0129")]

GUIDE = "Dr. JIM SOLOMON RAJA"
GUIDE_ID = "Employee ID: 22533 — SCOPE"


def upscale_architecture():
    """The supplied figure is 749x506; smooth it before it fills a slide."""
    if ARCH_HI.exists():
        return ARCH_HI
    im = Image.open(ARCH)
    if im.mode == "RGBA":
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.split()[3])
        im = flat
    im = im.convert("RGB").resize((im.width * 3, im.height * 3),
                                  Image.LANCZOS)
    im.save(ARCH_HI, "PNG", optimize=True)
    return ARCH_HI


# ===========================================================================
# 1. Title
# ===========================================================================
def slide_title(prs):
    slide = blank(prs, BG, card=True, card_alpha=84.0)

    tf = textbox(slide, BODY_L, CARD_T + Inches(0.52), BODY_W, Inches(0.3))
    line(tf, "B.TECH.  ·  BCSE497J — PROJECT-I  ·  "
             "COMPUTER SCIENCE AND ENGINEERING",
         first=True, size=11, bold=True, color=ACCENT, space_after=0)

    tf = textbox(slide, BODY_L, CARD_T + Inches(0.92), BODY_W, Inches(1.9))
    line(tf, TITLE, first=True, font=HEAD_FONT, size=23, bold=True,
         color=HEADING, line_spacing=1.14, space_after=0)

    rule = slide.shapes.add_shape(1, BODY_L, CARD_T + Inches(2.56),
                                  Inches(1.5), Pt(2.6))
    rule.fill.solid()
    rule.fill.fore_color.rgb = ACCENT
    rule.line.fill.background()

    tf = textbox(slide, BODY_L, CARD_T + Inches(2.86), Inches(5.9),
                 Inches(2.4))
    line(tf, "TEAM MEMBERS", first=True, size=10.5, bold=True, color=ACCENT,
         space_after=7)
    for name, reg in TEAM:
        p = line(tf, "", size=14.5, space_after=5)
        run(p, name, font=HEAD_FONT, size=14.5, bold=True, color=HEADING)
        run(p, f"   ({reg})", size=13, color=MUTED)

    tf = textbox(slide, BODY_L + Inches(6.3), CARD_T + Inches(2.86),
                 Inches(4.8), Inches(2.4))
    line(tf, "FACULTY GUIDE", first=True, size=10.5, bold=True, color=ACCENT,
         space_after=7)
    line(tf, GUIDE, font=HEAD_FONT, size=14.5, bold=True, color=HEADING,
         space_after=3)
    line(tf, GUIDE_ID, size=12, color=MUTED, space_after=14)
    line(tf, "School of Computer Science and Engineering", size=12,
         color=BODY, space_after=3)
    line(tf, "Vellore Institute of Technology, Vellore", size=12,
         color=BODY, space_after=0)

    tf = textbox(slide, BODY_L, CARD_T + CARD_H - Inches(0.62), BODY_W,
                 Inches(0.3))
    p = line(tf, "", first=True, size=11, space_after=0)
    run(p, "Review-3", size=11, bold=True, color=HEADING)
    run(p, "   ·   28 October 2026   ·   Fall Semester "
           "2026–2027", size=11, color=MUTED)


# ===========================================================================
# 2. Approval mail from guide
# ===========================================================================
def slide_approval(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Approval Mail From Guide", eyebrow="Review-3")

    tf = textbox(slide, BODY_L, y, BODY_W, Inches(0.8))
    line(tf, "Approval for the following aspects was obtained from the "
             "project guide by e-mail before 21-10-2026. All points raised "
             "have been addressed and updated by the project team.",
         first=True, size=14, color=BODY, space_after=0)

    y2 = y + Inches(0.72)
    items = [
        ("Project title", "Retained as filed in the patent application; "
                          "no change requested."),
        ("Problem statement and objectives",
         "Seven objectives, O1–O6 complete, O7 delivered in Phase II."),
        ("Architecture and modules",
         "Eleven-module pipeline and the edge-node block diagram approved."),
        ("Results and validation",
         "13 of 13 validation decisions verified in a live demonstration."),
        ("Outcome", "Patent route confirmed in place of conference or "
                    "journal publication."),
    ]
    tf = textbox(slide, BODY_L, y2, Inches(6.9), Inches(3.3))
    for lead, text in items:
        bullet(tf, text, lead=lead + "  —  ", size=13, space_after=9)

    callout(slide, BODY_L + Inches(7.25), y2, Inches(3.82), Inches(2.5),
            "Approval mail — screenshot",
            "Paste the guide's approval e-mail here before the review. "
            "Keep the sender address, subject line and date visible in the "
            "capture.",
            tint=RGBColor(0xFB, 0xF7, 0xE8), accent=WARN)

    callout(slide, BODY_L + Inches(7.25), y2 + Inches(2.70), Inches(3.82),
            Inches(0.86), "Status",
            "Approved · all review points closed", tint=RGBColor(
                0xEF, 0xF8, 0xEF), accent=OK)
    footer(slide, 2)


# ===========================================================================
# 3. Aim
# ===========================================================================
def slide_aim(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Aim", eyebrow="Objective of the work")

    tf = textbox(slide, BODY_L, y + Inches(0.1), BODY_W, Inches(1.5))
    p = line(tf, "", first=True, size=19, line_spacing=1.30, space_after=0)
    run(p, "To decide whether a retraining update for an edge-deployed IoT "
           "threat detector is safe to accept ", font=HEAD_FONT, size=19,
        color=HEADING)
    run(p, "before", font=HEAD_FONT, size=19, bold=True, italic=True,
        color=ACCENT)
    run(p, " it is accepted — by testing what the update would do to "
           "futures the system committed to in advance, rather than by "
           "testing what the update looks like.", font=HEAD_FONT, size=19,
        color=HEADING)

    y2 = y + Inches(1.78)
    cols = [
        ("Predict", "Mirror every device with a holographic digital twin "
                    "and commit 20 counterfactual futures before the "
                    "observation that will judge them exists."),
        ("Validate", "Graft each update onto a trusted core, train a shadow "
                     "model, and score it on six weighted components against "
                     "the committed futures."),
        ("Immunize", "Synthesise vaccine rows from those same futures so "
                     "resistance to a poisoning strategy exists before the "
                     "strategy is ever attempted."),
        ("Self-heal", "Restore the last trusted model and purge the "
                      "offending contributor's rows if degradation occurs "
                      "despite the gate."),
    ]
    w, gap = Inches(2.605), Inches(0.21)       # 4w + 3g == BODY_W
    for i, (t, txt) in enumerate(cols):
        callout(slide, BODY_L + i * (w + gap), y2, w, Inches(1.72), t, txt,
                title_size=14, text_size=11)

    tf = textbox(slide, BODY_L, y2 + Inches(2.00), BODY_W, Inches(0.5))
    p = line(tf, "", first=True, size=13, space_after=0)
    run(p, "Deliverable:  ", size=13, bold=True, color=ACCENT)
    run(p, "a working edge-gateway console in which all twelve stages of "
           "this cycle are operator-driven, inspectable and reproducible, "
           "on simulated devices and on live USB hardware alike.",
        size=13, color=BODY)
    footer(slide, 3)


# ===========================================================================
# 4. Abstract
# ===========================================================================
def slide_abstract(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Abstract", eyebrow="Summary")

    tf = textbox(slide, BODY_L, y, Inches(7.55), Inches(4.3))
    paras = [
        "Consumer IoT networks are increasingly defended by AI models that "
        "run on a local edge gateway and retrain continuously on the "
        "telemetry they collect. That retraining keeps the detector current "
        "— and is also its most exposed surface: an adversary who can "
        "introduce falsified or mislabelled training data can steer the "
        "model into accepting hostile behaviour as ordinary.",

        "Existing poisoning defences are reactive. Anomaly filtering, trust "
        "and reputation scoring and robust aggregation each inspect a "
        "contribution only after submission, and judge it only against "
        "present or historical observations — so a contribution "
        "engineered to resemble ordinary traffic passes unchallenged.",

        "This project develops a proactive alternative. Every device is "
        "mirrored by a holographic digital twin that models it as five "
        "behavioural planes and commits in advance to twenty counterfactual "
        "futures. An incoming update is grafted onto a trusted core, a "
        "shadow model is trained, and its behaviour on that audit bank "
        "yields a Counterfactual Consistency Score judged against a "
        "threshold calibrated from honest traffic on that specific fleet.",

        "The framework is implemented end to end and evaluated on a "
        "simulated eight-device network and on live USB hardware against "
        "five poisoning strategies, including clean-label poisoning that "
        "carries no label shift and is therefore invisible to "
        "distributional defences.",
    ]
    for i, t in enumerate(paras):
        line(tf, t, first=(i == 0), size=12.5, color=BODY, space_after=9,
             line_spacing=1.16, align=PP_ALIGN.JUSTIFY)

    x = BODY_L + Inches(7.95)
    w = Inches(3.12)
    callout(slide, x, y, w, Inches(1.30), "The core idea",
            "Judge an update by its consequence on committed futures, not "
            "by its resemblance to the present.")
    for i, (val, lab) in enumerate([("0.9565", "Detection accuracy"),
                                    ("13 / 13", "Correct decisions"),
                                    ("0.9736", "Poison resistance")]):
        stat(slide, x, y + Inches(1.52) + i * Inches(0.84), w, val, lab)

    tf = textbox(slide, BODY_L, y + Inches(4.30), Inches(7.55), Inches(0.5))
    p = line(tf, "", first=True, size=11, space_after=0)
    run(p, "Keywords — ", size=11, bold=True, color=ACCENT)
    run(p, "Digital Twin · Counterfactual Validation · Model "
           "Poisoning · Edge AI · Consumer IoT Security · "
           "Predictive Immunization · Self-Healing Systems",
        size=11, italic=True, color=MUTED)
    footer(slide, 4)


# ===========================================================================
# 5. Literature review
# ===========================================================================
def slide_literature(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Literature Review", eyebrow="Prior work")

    rows = [
        ["Work", "Contribution", "Limitation for this problem"],
        ["Alcaraz & Lopez, 2022\nIEEE COMST",
         "Comprehensive survey of digital-twin security threats.",
         "Treats the twin as an asset to protect, never as a validator."],
        ["Tian et al., 2022\nACM Comput. Surv.",
         "Taxonomy of poisoning attacks and countermeasures.",
         "Every countermeasure surveyed acts after submission."],
        ["Nguyen et al., 2019\nICDCS — DÏoT",
         "Federated self-learning anomaly detection for IoT.",
         "Aggregation assumes most contributors are honest."],
        ["Shafahi et al., 2018\nNeurIPS — Poison Frogs",
         "Clean-label poisoning with no label shift at all.",
         "Defeats the whole family of distributional defences."],
        ["Fung et al., 2020\nRAID",
         "Limits of federated learning under Sybil pressure.",
         "Identifies the failure; proposes no forward-looking gate."],
        ["Sulem et al., 2022\narXiv:2203.11103",
         "Counterfactual explanations for time-series anomalies.",
         "Explains a past decision; does not gate a future one."],
    ]
    table(slide, rows, [2.30, 4.25, 4.55], BODY_L, y,
          head_size=11.5, body_size=10.5, row_h=0.56, head_h=0.38)

    tf = textbox(slide, BODY_L, y + Inches(3.90), BODY_W, Inches(0.8))
    p = line(tf, "", first=True, size=12.5, space_after=0, line_spacing=1.18)
    run(p, "Reading across the field:  ", size=12.5, bold=True, color=ACCENT)
    run(p, "digital twins are used for monitoring, counterfactuals for "
           "explanation, and poisoning defences for filtering — but no "
           "work joins them into a decision mechanism that validates a model "
           "update against futures committed before the update existed.",
        size=12.5, color=BODY)
    footer(slide, 5)


# ===========================================================================
# 6. Research gap
# ===========================================================================
def slide_gap(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Research Gap", eyebrow="What is missing")

    left = [
        ("G1  Validation against the current state only.  ",
         "Trust, reputation and robust aggregation compare an update with "
         "the present or the past. None tests it against where the device "
         "is expected to go next."),
        ("G2  Twins and counterfactuals are never combined.  ",
         "Each has been applied separately; neither has been joined into a "
         "gate on model updates."),
        ("G3  Attack simulation does not close the loop.  ",
         "Simulation measures accuracy, then stops. It is rarely carried on "
         "to synthesise training rows and retrain."),
        ("G4  Twins monitor rather than immunize.  ",
         "Twin research targets visualisation and fault prediction, not "
         "active prediction of behaviour under attack."),
    ]
    right = [
        ("G5  Detection remains reactive.  ",
         "Attack → collect → detect → alert. Prediction is "
         "seldom tied to proactive adaptation at the edge."),
        ("G6  Clean-label poisoning passes everything.  ",
         "Defences that filter on label distribution cannot see an attack "
         "that alters no label."),
        ("G7  Retraining forces a security trade-off.  ",
         "Frequent retraining adapts but widens exposure; infrequent is "
         "safer but stale. Choosing a frequency resolves neither."),
        ("G8  Recovery is manual and total.  ",
         "Restoring a clean model is an operator task, and the usual remedy "
         "discards the entire training pool."),
    ]
    for items, x in ((left, BODY_L),
                     (right, BODY_L + Inches(5.70))):
        tf = textbox(slide, x, y, Inches(5.40), Inches(3.4))
        for lead, text in items:
            bullet(tf, text, lead=lead, size=12, space_after=10)

    tf = textbox(slide, BODY_L, y + Inches(3.42), BODY_W, Inches(0.9))
    p = line(tf, "", first=True, size=12.5, space_after=0, line_spacing=1.18,
             align=PP_ALIGN.JUSTIFY)
    run(p, "Stated as one gap:  ", size=12.5, bold=True, color=ACCENT)
    run(p, "there is no integrated framework that uses counterfactual twin "
           "states to validate machine-learning updates against multiple "
           "plausible future behaviours, quarantines the inconsistent ones, "
           "and proactively immunizes the edge model against threats it has "
           "not yet met.", size=12.5, color=BODY)
    footer(slide, 6)


# ===========================================================================
# 7. Objectives
# ===========================================================================
def slide_objectives(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Objectives", eyebrow="Seven, each with a gate")

    rows = [
        ["#", "Objective", "Gap", "Measurable criterion", "Status"],
        ["O1", "Simulate a heterogeneous consumer IoT fleet and an "
               "on-demand edge gateway.", "G4",
         "Six device types separable on baseline", "Complete"],
        ["O2", "Build a holographic twin per device across five "
               "behavioural planes.", "G4",
         "Zero false flags on healthy traffic", "Complete"],
        ["O3", "Commit counterfactual futures before the observation "
               "they judge exists.", "G1",
         "20 futures × 5-tick horizon, in advance", "Complete"],
        ["O4", "Design a Counterfactual Consistency Score gating every "
               "retraining update.", "G2",
         "Separation of honest from poisoned scores", "Complete"],
        ["O5", "Detect clean-label poisoning carrying no label shift.",
         "G6", "Quarantined at label shift below 0.10", "Complete"],
        ["O6", "Immunize the detector against synthesised poisoning "
               "before real attacks.", "G3",
         "Resistance measured across five strategies", "Complete"],
        ["O7", "Benchmark against reactive baselines across poisoning "
               "rates.", "G1", "Attack success rate vs. each baseline",
         "Phase II"],
    ]
    gf = table(slide, rows, [0.42, 4.20, 0.52, 3.55, 0.90], BODY_L, y,
               head_size=10.5, body_size=9.8, row_h=0.345, head_h=0.34)
    tbl = gf.table
    for r in range(1, len(rows)):
        cell = tbl.cell(r, 4)
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.runs[0].font.bold = True
        p.runs[0].font.color.rgb = OK if rows[r][4] == "Complete" else WARN
        tbl.cell(r, 0).text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        tbl.cell(r, 2).text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    y2 = y + Inches(2.96)
    callout(slide, BODY_L, y2, Inches(5.40), Inches(1.28),
            "Sustainable Development Goals",
            "SDG 9 — Industry, Innovation and Infrastructure   ·   "
            "SDG 11 — Sustainable Cities and Communities   ·   "
            "SDG 16 — Peace, Justice and Strong Institutions",
            title_size=13, text_size=11)
    callout(slide, BODY_L + Inches(5.70), y2, Inches(5.40), Inches(1.28),
            "Outcome identified",
            "PATENT  —  Indian Patent Application filed for the "
            "counterfactual-driven adaptive security control method.",
            tint=RGBColor(0xEF, 0xF8, 0xEF), accent=OK,
            title_size=13, text_size=11)
    footer(slide, 7)


# ===========================================================================
# 8. Framework / architecture
# ===========================================================================
def slide_architecture(prs, arch):
    slide = blank(prs, BG)
    y = heading(slide, "Framework / Architecture / Block Diagram",
                eyebrow="System architecture", size=28)

    # The supplied figure carries its own FIG. 1 caption, so none is added.
    im = Image.open(arch)
    max_w, max_h = Inches(9.05), Inches(4.60)
    scale = min(max_w / im.width, max_h / im.height)
    w, h = int(im.width * scale), int(im.height * scale)
    slide.shapes.add_picture(str(arch), BODY_L, y + Inches(0.04), w, h)

    x = BODY_L + Inches(9.28)
    cw = Inches(1.80)
    notes = [
        ("102", "Consumer IoT devices — camera, thermostat, lighting, "
                "lock, wearable."),
        ("106", "Edge node: the gateway where every decision is taken."),
        ("108", "Digital-twin state store — current, historical, "
                "profiles, baselines."),
        ("112", "Counterfactual scenario generator: the committed futures."),
        ("116", "Scenario assessment — risk, likelihood, "
                "prioritisation."),
        ("118", "Security-control decision support and policy update."),
    ]
    tf = textbox(slide, x, y + Inches(0.06), cw, Inches(4.4))
    for i, (num, text) in enumerate(notes):
        p = line(tf, "", first=(i == 0), size=9.5, space_after=8,
                 line_spacing=1.12)
        run(p, num + "  ", size=9.5, bold=True, color=ACCENT)
        run(p, text, size=9.5, color=BODY)

    footer(slide, 8)


# ===========================================================================
# 9. Functional requirements
# ===========================================================================
def slide_requirements(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Functional Requirements", eyebrow="FR-01 to FR-10")

    left = [
        ("FR-01  Device simulation.  ",
         "Continuous sixteen-feature telemetry for six device types, "
         "deformable by a named attack class on demand."),
        ("FR-02  On-demand ingestion.  ",
         "The gateway collects, timestamps and buffers telemetry only when "
         "an operator requests a tick."),
        ("FR-03  Twin synchronisation.  ",
         "Each twin updates its five-plane state from trusted telemetry and "
         "refuses any observation judged hostile."),
        ("FR-04  Future commitment.  ",
         "Every ready twin commits twenty trajectories over a five-tick "
         "horizon before the judging observation exists."),
        ("FR-05  Threat detection.  ",
         "Classify normal traffic and six attack classes, returning class, "
         "confidence and an operator-facing risk level."),
    ]
    right = [
        ("FR-06  Counterfactual validation.  ",
         "Score every update on six weighted components against the audit "
         "bank, versus a fleet-calibrated threshold."),
        ("FR-07  Operator control.  ",
         "Apply accept or quarantine only on explicit instruction; allow "
         "override in either direction and record it."),
        ("FR-08  Quarantine ledger.  ",
         "Retain quarantined updates intact with id, source, strategy, "
         "score and timestamp, and allow rescoring."),
        ("FR-09  Predictive immunization.  ",
         "Synthesise vaccine rows from committed futures and measure poison "
         "resistance across five strategies."),
        ("FR-10  Guarded promotion.  ",
         "Promote a candidate only if accuracy, resistance, false-positive "
         "rate and pool size all pass; else roll back."),
    ]
    for items, x in ((left, BODY_L), (right, BODY_L + Inches(5.70))):
        tf = textbox(slide, x, y, Inches(5.40), Inches(4.2))
        for lead, text in items:
            bullet(tf, text, lead=lead, size=12, space_after=11)
    footer(slide, 9)


# ===========================================================================
# 10. Modules
# ===========================================================================
def slide_modules(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Modules", eyebrow="Eleven packages, one stage each")

    rows = [
        ["Module", "Responsibility", "Key artefact"],
        ["simulator", "Six device profiles, per-attack deformations and the "
                      "labelled corpus generator.", "SimulatedDevice"],
        ["live", "Real USB peripherals via Windows PnP; host telemetry via "
                 "psutil.", "UsbMonitor, HostSampler"],
        ["twin", "Five planes, a ridge vector-autoregressive forward model "
                 "and committed futures.", "HolographicTwin"],
        ["detection", "Feature engineering and the edge threat classifier.",
         "ThreatDetector"],
        ["counterfactual", "The audit bank and the Counterfactual "
                           "Consistency Score.", "CounterfactualValidator"],
        ["poisoning", "Five poisoning strategies used to test the defence.",
         "PoisonForge"],
        ["immunization", "Predictive vaccines and poison-resistance "
                         "measurement.", "ImmunizationEngine"],
        ["quarantine", "Holding, dissecting, releasing and rescoring "
                       "updates.", "QuarantineZone"],
        ["retraining", "Validated safe pool, promotion gates and versioned "
                       "registry.", "SecureRetrainer"],
        ["selfheal", "Model/twin agreement monitoring, rollback and purge.",
         "SelfHealingMonitor"],
        ["server", "Operator console, JSON API, accounts, sessions and the "
                   "audit database.", "pages.py, auth.py, db.py"],
    ]
    gf = table(slide, rows, [1.55, 6.20, 3.35], BODY_L, y,
               head_size=10.5, body_size=9.8, row_h=0.305, head_h=0.33)
    tbl = gf.table
    for r in range(1, len(rows)):
        for c in (0, 2):
            rn = tbl.cell(r, c).text_frame.paragraphs[0].runs[0]
            rn.font.name = "Consolas"
            rn.font.size = Pt(9.3)
            rn.font.color.rgb = ACCENT if c == 0 else MUTED
            rn.font.bold = (c == 0)

    tf = textbox(slide, BODY_L, y + Inches(3.88), BODY_W, Inches(0.6))
    p = line(tf, "", first=True, size=12, space_after=0, line_spacing=1.18)
    run(p, "Why the boundaries matter:  ", size=12, bold=True, color=ACCENT)
    run(p, "no module reaches across more than one boundary, which is what "
           "lets the simulated fleet and the live USB sampler be swapped "
           "for one another without any stage above Step 1 being aware of "
           "the change.", size=12, color=BODY)
    footer(slide, 10)


# ===========================================================================
# 11. Experiments and results
# ===========================================================================
def slide_results(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Experiments and Results",
                eyebrow="Eight-device fleet, seed 1337")

    for i, (val, lab, col) in enumerate([
            ("0.9565", "Detection accuracy", ACCENT),
            ("0.0307", "False-negative rate", ACCENT),
            ("0.8568", "Calibrated accept gate", ACCENT),
            ("13 / 13", "Correct decisions", OK),
            ("0.9736", "Poison resistance", OK)]):
        stat(slide, BODY_L + i * Inches(2.26), y, Inches(2.10), val, lab,
             color=col, value_size=23, label_size=9.5)

    y2 = y + Inches(0.98)
    tf = textbox(slide, BODY_L, y2 - Inches(0.26), Inches(6.60), Inches(0.3))
    line(tf, "VALIDATION DECISIONS — 13 SUBMITTED, 1 HONEST",
         first=True, size=9.5, bold=True, color=MUTED, space_after=0)

    rows = [
        ["Crafted as", "CCS", "Gate", "Decision"],
        ["Honest contribution", "0.910", "0.857", "ACCEPTED"],
        ["Label flipping", "0.629", "0.857", "QUARANTINED"],
        ["Gradual poisoning", "0.801", "0.857", "QUARANTINED"],
        ["Backdoor trigger", "0.659", "0.857", "QUARANTINED"],
        ["Sybil flood (8 shards)", "0.677–0.730", "0.907",
         "QUARANTINED"],
        ["Clean-label poisoning", "0.735", "0.907", "QUARANTINED"],
    ]
    gf = table(slide, rows, [2.55, 1.30, 1.05, 1.70], BODY_L, y2,
               head_size=10.5, body_size=10, row_h=0.325, head_h=0.33,
               aligns=[PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.CENTER,
                       PP_ALIGN.CENTER])
    tbl = gf.table
    for r in range(1, len(rows)):
        rn = tbl.cell(r, 3).text_frame.paragraphs[0].runs[0]
        rn.font.bold = True
        rn.font.size = Pt(9.5)
        rn.font.color.rgb = OK if rows[r][3] == "ACCEPTED" else WARN

    x = BODY_L + Inches(7.10)
    tf = textbox(slide, x, y2 - Inches(0.26), Inches(4.0), Inches(0.3))
    line(tf, "LIVE USB HARDWARE vs. SIMULATED FLEET", first=True, size=9.5,
         bold=True, color=MUTED, space_after=0)
    table(slide, [
        ["Metric", "Live USB", "Simulated"],
        ["Accuracy", "0.9962", "0.9565"],
        ["Macro F1", "0.9961", "0.9564"],
        ["False-positive rate", "0.0000", "0.0488"],
        ["False-negative rate", "0.0029", "0.0307"],
        ["Validation decisions", "13 of 13", "13 of 13"],
    ], [2.05, 1.05, 1.10], x, y2, head_size=10.5, body_size=10,
        row_h=0.325, head_h=0.33,
        aligns=[PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.CENTER])

    tf = textbox(slide, BODY_L, y2 + Inches(2.32), BODY_W, Inches(0.95))
    p = line(tf, "", first=True, size=11.5, space_after=5, line_spacing=1.16,
             align=PP_ALIGN.JUSTIFY)
    run(p, "Clean-label is the decisive row.  ", size=11.5, bold=True,
        color=ACCENT)
    run(p, "Its label mix barely moves, so every distributional check admits "
           "it; it is caught only by cross-checking its labels against the "
           "trusted model's own reading of its rows. Sybil shards face a "
           "0.907 gate rather than 0.857 because the burst of unseen "
           "contributor identities triggers the novelty penalty.",
        size=11.5, color=BODY)
    p = line(tf, "", size=11.5, space_after=0, line_spacing=1.16,
             align=PP_ALIGN.JUSTIFY)
    run(p, "Read the live column carefully:  ", size=11.5, bold=True,
        color=WARN)
    run(p, "it reflects an easier problem, not a better model — USB "
           "peripherals all sample one host, so their baselines nearly "
           "coincide and the class overlap of the mixed fleet disappears.",
        size=11.5, color=BODY)
    footer(slide, 11)


# ===========================================================================
# 12. Conclusion and future work
# ===========================================================================
def slide_conclusion(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Conclusion and Future Work", eyebrow="Where it lands")

    tf = textbox(slide, BODY_L, y, Inches(6.55), Inches(1.5))
    line(tf, "Existing defences judge an incoming contribution by how "
             "closely it resembles the others — a question about the "
             "present and the past, which an attacker answers by staying "
             "close to the crowd. This framework asks instead what "
             "accepting the update would cost the system's ability to "
             "detect tomorrow's attack.",
         first=True, size=12, color=BODY, line_spacing=1.16,
         space_after=10, align=PP_ALIGN.JUSTIFY)

    tf = textbox(slide, BODY_L, y + Inches(1.26), Inches(6.55), Inches(2.6))
    line(tf, "CONTRIBUTIONS", first=True, size=9.5, bold=True, color=MUTED,
         space_after=7)
    for t in [
            "A validation mechanism that judges an update by its effect on "
            "futures committed before the update existed.",
            "A six-component Consistency Score in which each term closes a "
            "hole the others leave open.",
            "Run-time threshold calibration that adapts the gate to the "
            "deployed fleet rather than to a fixed constant.",
            "A predictive immunization engine that inoculates the edge "
            "model against poisoning it has not yet met.",
            "An operator console in which every stage is a deliberate, "
            "inspectable action with declared prerequisites."]:
        bullet(tf, t, size=11, space_after=6)

    x = BODY_L + Inches(6.95)
    tf = textbox(slide, x, y, Inches(4.15), Inches(0.3))
    line(tf, "FUTURE WORK", first=True, size=9.5, bold=True, color=MUTED,
         space_after=0)
    tf = textbox(slide, x, y + Inches(0.30), Inches(4.15), Inches(2.4))
    for t in [
            "Deployment against genuine networked IoT hardware with its own "
            "address, removing the host-attribution assumption.",
            "Extension of the poisoning taxonomy, and an adaptive adversary "
            "that knows the Consistency Score itself.",
            "A learned strategy attributor in place of the rule-based one.",
            "Evaluation across cooperating gateways, sharing the "
            "counterfactual bank without sharing telemetry."]:
        bullet(tf, t, size=11.5, space_after=8)

    callout(slide, x, y + Inches(2.92), Inches(4.15), Inches(1.30),
            "Independent of its data source",
            "Real USB peripherals were enrolled through the identical "
            "twelve stages, with the provenance of all sixteen features "
            "declared and the two unobtainable ones reported missing rather "
            "than fabricated.", title_size=12, text_size=10.5)

    tf = textbox(slide, BODY_L, y + Inches(4.06), Inches(6.55), Inches(0.7))
    p = line(tf, "", first=True, size=11.5, space_after=0, line_spacing=1.16,
             align=PP_ALIGN.JUSTIFY)
    run(p, "The framework establishes that counterfactual consequence is a "
           "usable and discriminating basis for deciding whether to accept "
           "a model update at the edge — and that the decision can be "
           "taken on hardware a household already owns.", size=11.5,
        italic=True, color=HEADING)
    footer(slide, 12)


# ===========================================================================
# 13. Outcome achieved
# ===========================================================================
def slide_outcome(prs):
    slide = blank(prs, BG)
    y = heading(slide, "Outcome Achieved", eyebrow="Review-3 deliverable")

    box = callout(slide, BODY_L, y, BODY_W, Inches(1.16), "PATENT",
                  "Indian Patent Application — “System and Method "
                  "for Counterfactual-Driven Adaptive Security Control and "
                  "Verified Model Updating in Edge-Deployed Digital Twins "
                  "for Consumer Internet of Things Networks”",
                  tint=RGBColor(0xEF, 0xF8, 0xEF), accent=OK,
                  title_size=22, text_size=12.5, align=PP_ALIGN.CENTER)

    y2 = y + Inches(1.40)
    cards = [
        ("Application", "Indian Patent Application\nfiled at the Indian "
                        "Patent Office"),
        ("Status", "FILED\nawaiting publication"),
        ("Inventors", "Three student inventors\nwith the project guide"),
        ("Artefact", "Complete specification,\nclaims and Fig. 1"),
    ]
    w, gap = Inches(2.605), Inches(0.21)       # 4w + 3g == BODY_W
    for i, (t, txt) in enumerate(cards):
        callout(slide, BODY_L + i * (w + gap), y2, w, Inches(1.26), t, txt,
                title_size=13, text_size=11, align=PP_ALIGN.CENTER)

    y3 = y2 + Inches(1.54)
    tf = textbox(slide, BODY_L, y3, Inches(6.9), Inches(1.5))
    line(tf, "WHY THE PATENT ROUTE", first=True, size=9.5, bold=True,
         color=MUTED, space_after=7)
    for t in ["The contribution is a method, not a measurement — a "
              "decision mechanism that can be claimed.",
              "The committed-futures invariant is implementable on any edge "
              "gateway, independent of the model family.",
              "A filed application secures priority on the mechanism "
              "while Phase II benchmarking continues."]:
        bullet(tf, t, size=11.5, space_after=7)

    callout(slide, BODY_L + Inches(7.25), y3, Inches(3.82), Inches(1.42),
            "Proof of outcome — to upload",
            "Patent filing receipt / acknowledgement screenshot to be "
            "uploaded on or before 27 Oct 2026 at the link circulated with "
            "the Review-3 template.",
            tint=RGBColor(0xFB, 0xF7, 0xE8), accent=WARN,
            title_size=12, text_size=10.5)
    footer(slide, 13)


# ===========================================================================
# 14. References
# ===========================================================================
def slide_references(prs):
    slide = blank(prs, BG)
    y = heading(slide, "References", eyebrow="IEEE format")

    left = [
        "C. Alcaraz and J. Lopez, “Digital twin: A comprehensive survey "
        "of security threats,” IEEE Commun. Surveys Tuts., vol. 24, "
        "no. 3, pp. 1475–1503, 2022.",
        "Z. Tian, L. Cui, J. Liang, and S. Yu, “A comprehensive survey "
        "on poisoning attacks and countermeasures in machine learning,” "
        "ACM Comput. Surv., vol. 55, no. 8, pp. 1–35, 2022.",
        "R. Yang, H. He, Y. Wang, Y. Qu, and W. Zhang, “Dependable "
        "federated learning for IoT intrusion detection against poisoning "
        "attacks,” Computers & Security, vol. 132, art. 103381, 2023.",
        "T. D. Nguyen et al., “DÏoT: A federated self-learning "
        "anomaly detection system for IoT,” in Proc. IEEE ICDCS, "
        "Dallas, TX, USA, 2019, pp. 756–767.",
        "D. Sulem et al., “Diverse counterfactual explanations for "
        "anomaly detection in time series,” arXiv:2203.11103, 2022.",
    ]
    right = [
        "A. Shafahi et al., “Poison frogs! Targeted clean-label "
        "poisoning attacks on neural networks,” in Adv. Neural Inf. "
        "Process. Syst. (NeurIPS), 2018.",
        "E. Bagdasaryan, A. Veit, Y. Hua, D. Estrin, and V. Shmatikov, "
        "“How to backdoor federated learning,” in Proc. AISTATS, "
        "2020, pp. 2938–2948.",
        "V. Tolpegin, S. Truex, M. E. Gursoy, and L. Liu, “Data "
        "poisoning attacks against federated learning systems,” in "
        "Proc. ESORICS, 2020, pp. 480–501.",
        "C. Fung, C. J. M. Yoon, and I. Beschastnikh, “The limitations "
        "of federated learning in Sybil settings,” in Proc. RAID, 2020, "
        "pp. 301–316.",
        "M. Antonakakis et al., “Understanding the Mirai botnet,” "
        "in Proc. 26th USENIX Security Symp., 2017, pp. 1093–1110.",
    ]
    n = 1
    for items, x in ((left, BODY_L), (right, BODY_L + Inches(5.70))):
        tf = textbox(slide, x, y, Inches(5.40), Inches(4.2))
        for i, text in enumerate(items):
            p = line(tf, "", first=(i == 0), size=11.5, space_after=11,
                     line_spacing=1.15, align=PP_ALIGN.JUSTIFY)
            from deck_theme import _hanging
            _hanging(p, 0.34)
            run(p, f"[{n}]  ", size=11.5, bold=True, color=ACCENT)
            run(p, text, size=11.5, color=BODY)
            n += 1
    footer(slide, 14)


# ===========================================================================
def main() -> int:
    make_background(BG)
    arch = upscale_architecture()

    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H

    # Authorship on the file itself, not the library's defaults.
    props = prs.core_properties
    props.author = TEAM[1][0].title()
    props.last_modified_by = props.author
    props.title = TITLE
    props.subject = "BCSE497J Project-I — Review-3"
    props.comments = ""
    props.category = ""
    props.keywords = ""

    slide_title(prs)
    slide_approval(prs)
    slide_aim(prs)
    slide_abstract(prs)
    slide_literature(prs)
    slide_gap(prs)
    slide_objectives(prs)
    slide_architecture(prs, arch)
    slide_requirements(prs)
    slide_modules(prs)
    slide_results(prs)
    slide_conclusion(prs)
    slide_outcome(prs)
    slide_references(prs)

    prs.save(OUT)
    print(f"wrote {OUT}  ({OUT.stat().st_size // 1024} KB, "
          f"{len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
