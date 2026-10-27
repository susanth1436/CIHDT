"""Build the BCSE497J Project-I report to the faculty template.

    python report/build_report.py

Writes report/CIHDT_ProjectI_Report.docx.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from docx import Document                                        # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK          # noqa: E402
from docx.shared import Inches, Pt                               # noqa: E402

from docx_kit import (body, bookmark, bullet, cell_text,          # noqa: E402
                      clear_cell_borders, figure, grid, h1, h2, h3,
                      new_section, numbered, page_numbering, pageref, para)
from chapters_late import (appendix_a, chapter_5, chapter_6,     # noqa: E402
                           chapter_7, chapter_8)
import front_matter as fm                                       # noqa: E402

FIG = HERE / "figures"
OUT = HERE / "CIHDT_ProjectI_Report.docx"

TITLE = ("SYSTEM AND METHOD FOR COUNTERFACTUAL-DRIVEN ADAPTIVE SECURITY "
         "CONTROL AND VERIFIED MODEL UPDATING IN EDGE-DEPLOYED DIGITAL TWINS "
         "FOR CONSUMER INTERNET OF THINGS NETWORKS")

# Sorted on register number, as the template requires.
TEAM = [("23BAI0136", "ATRIK"),
        ("23BCI0231", "T V SAI SUSANTH"),
        ("23BCT0129", "PUSHPAK")]

GUIDE = "Dr. JIM SOLOMON RAJA"
GUIDE_DESIGNATION = "Employee ID: 22533"
SCHOOL = "School of Computer Science and Engineering (SCOPE)"
MONTH = "October 2026"

C = WD_ALIGN_PARAGRAPH.CENTER
L = WD_ALIGN_PARAGRAPH.LEFT


# ===========================================================================
# Cover page
# ===========================================================================
def cover(doc):
    para(doc, "BCSE497J - Project-I", size=18, bold=True, align=C, line=1.5,
         before=6, after=26)
    para(doc, TITLE, size=16, bold=True, align=C, line=1.5, after=26)

    para(doc, "Submitted in partial fulfilment of the requirements for the "
              "degree of", size=12, align=C, line=1.5, after=6)
    para(doc, "B.Tech.", size=14, bold=True, align=C, line=1.5, after=2)
    para(doc, "in", size=12, align=C, line=1.5, after=2)
    para(doc, "Computer Science and Engineering", size=14, bold=True,
         align=C, line=1.5, after=22)

    para(doc, "by", size=12, align=C, line=1.5, after=8)
    for reg, name in TEAM:
        para(doc, reg, size=13, bold=True, align=C, line=1.5, after=0)
        para(doc, name, size=13, bold=True, align=C, line=1.5, after=8)

    para(doc, "Under the Supervision of", size=12, align=C, line=1.5,
         before=16, after=6)
    para(doc, GUIDE, size=14, bold=True, align=C, line=1.5, after=2)
    para(doc, GUIDE_DESIGNATION, size=12, align=C, line=1.5, after=2)
    para(doc, SCHOOL, size=12, align=C, line=1.5, after=22)

    para(doc, "School of Computer Science and Engineering", size=13,
         bold=True, align=C, line=1.5, after=4)
    para(doc, "Vellore Institute of Technology, Vellore - 632 014", size=12,
         align=C, line=1.5, after=20)
    para(doc, MONTH, size=13, bold=True, align=C, line=1.5, after=0)


# ===========================================================================
# Abstract
# ===========================================================================
def abstract(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    p = para(doc, "ABSTRACT", size=16, bold=True, align=C, line=1.5,
             before=0, after=14)
    bookmark(p, "bm_abstract")

    body(doc, "Consumer Internet-of-Things networks — smart cameras, locks, "
              "plugs, bulbs, sensors and speakers — are increasingly defended "
              "by artificial-intelligence models that execute on a local edge "
              "gateway and retrain continuously on the telemetry they collect. "
              "That continuous retraining is what keeps the detector current "
              "as a household's devices and habits change, and it is also the "
              "system's most exposed surface: an adversary able to introduce "
              "falsified or mislabelled training data can steer the model into "
              "accepting hostile behaviour as ordinary. Existing poisoning "
              "defences are reactive. Anomaly filtering, trust and reputation "
              "scoring, and robust aggregation each inspect a contribution "
              "only after it has been submitted, and each judges it only "
              "against present or historical observations, so a contribution "
              "engineered to resemble ordinary traffic passes unchallenged.")

    body(doc, "This project develops a proactive alternative. Every physical "
              "device is mirrored by a holographic digital twin that models "
              "the device as five partial behavioural projections and commits, "
              "in advance, to twenty counterfactual future trajectories "
              "describing how that device would behave if nothing were wrong. "
              "Those futures — half left benign, half deformed by each attack "
              "class in the taxonomy — form an audit bank. An incoming "
              "retraining update is grafted onto a small trusted core, a "
              "shadow model is trained, and the shadow model's behaviour on "
              "the audit bank yields a Counterfactual Consistency Score, "
              "judged against a threshold calibrated from honest traffic on "
              "that specific fleet. A predictive immunization engine "
              "synthesises vaccine rows from the same committed futures so "
              "that resistance exists before any real attack is attempted, and "
              "a self-healing controller restores the last trusted model and "
              "purges the offending contributor's rows should degradation "
              "nonetheless occur.")

    body(doc, "The framework has been implemented end to end and evaluated on "
              "a simulated eight-device network against five poisoning "
              "strategies, including clean-label poisoning that carries no "
              "label shift and is therefore invisible to distributional "
              "defences.")

    para(doc, "Keywords — Digital Twin, Counterfactual Validation, Model "
              "Poisoning, Edge Artificial Intelligence, Consumer IoT "
              "Security, Predictive Immunization, Self-Healing Systems.",
         size=12, italic=True, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=1.15,
         before=10, after=0)


# ===========================================================================
# Table of contents
# ===========================================================================
TOC_ENTRIES = [
    ("", "Abstract", "bm_abstract", True),
    ("1.", "INTRODUCTION", "bm_1", True),
    ("", "1.1  Background", "bm_1_1", False),
    ("", "1.2  Motivation", "bm_1_2", False),
    ("", "1.3  Scope of the Project", "bm_1_3", False),
    ("2.", "PROJECT DESCRIPTION AND GOALS", "bm_2", True),
    ("", "2.1  Literature Review", "bm_2_1", False),
    ("", "2.2  Research Gap", "bm_2_2", False),
    ("", "2.3  Objectives", "bm_2_3", False),
    ("", "2.4  Problem Statement", "bm_2_4", False),
    ("", "2.5  Project Plan", "bm_2_5", False),
    ("3.", "TECHNICAL SPECIFICATION", "bm_3", True),
    ("", "3.1  Requirements", "bm_3_1", False),
    ("", "3.1.1  Functional", "bm_3_1_1", False),
    ("", "3.1.2  Non-Functional", "bm_3_1_2", False),
    ("", "3.2  Feasibility Study", "bm_3_2", False),
    ("", "3.2.1  Technical Feasibility", "bm_3_2_1", False),
    ("", "3.2.2  Economic Feasibility", "bm_3_2_2", False),
    ("", "3.2.3  Social Feasibility", "bm_3_2_3", False),
    ("", "3.3  System Specification", "bm_3_3", False),
    ("", "3.3.1  Hardware Specification", "bm_3_3_1", False),
    ("", "3.3.2  Software Specification", "bm_3_3_2", False),
    ("4.", "DESIGN APPROACH AND DETAILS", "bm_4", True),
    ("", "4.1  System Architecture", "bm_4_1", False),
    ("", "4.2  Design", "bm_4_2", False),
    ("", "4.2.1  Data Flow Diagram", "bm_4_2_1", False),
    ("", "4.2.2  Use Case Diagram", "bm_4_2_2", False),
    ("", "4.2.3  Class Diagram", "bm_4_2_3", False),
    ("", "4.2.4  Sequence Diagram", "bm_4_2_4", False),
    ("5.", "METHODOLOGY AND TESTING", "bm_5", True),
    ("", "5.1  Module Description", "bm_5_1", False),
    ("", "5.2  Methodology", "bm_5_2", False),
    ("", "5.3  Testing", "bm_5_3", False),
    ("6.", "PROJECT DEMONSTRATION", "bm_6", True),
    ("", "6.1  Access Control", "bm_6_1", False),
    ("", "6.2  Walking the Twelve Steps", "bm_6_2", False),
    ("", "6.3  Demonstration on Live USB Hardware", "bm_6_3", False),
    ("", "6.4  Conclusion of a Run", "bm_6_4", False),
    ("7.", "RESULT AND DISCUSSION", "bm_7", True),
    ("", "7.1  Threat Detection Performance", "bm_7_1", False),
    ("", "7.2  Twin Consistency", "bm_7_2", False),
    ("", "7.3  Counterfactual Validation", "bm_7_3", False),
    ("", "7.4  Immunization and Promotion", "bm_7_4", False),
    ("", "7.5  Results on Live USB Hardware", "bm_7_5", False),
    ("", "7.6  Cost Analysis", "bm_7_6", False),
    ("", "7.7  Discussion", "bm_7_7", False),
    ("8.", "CONCLUSION", "bm_8", True),
    ("", "8.1  Contributions", "bm_8_1", False),
    ("", "8.2  Future Work", "bm_8_2", False),
    ("9.", "REFERENCES", "bm_9", True),
    ("", "APPENDIX A \u2014 SAMPLE CODE", "bm_appendix", True),
]


def table_of_contents(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    para(doc, "TABLE OF CONTENTS", size=14, bold=True, align=C, line=1.5,
         after=12)

    table = doc.add_table(rows=len(TOC_ENTRIES) + 1, cols=3)
    widths = (0.85, 4.95, 1.10)
    head = ("Sl.No", "Contents", "Page No.")
    for c, text in enumerate(head):
        cell = table.cell(0, c)
        cell.width = Inches(widths[c])
        clear_cell_borders(cell)
        cell_text(cell, text, size=12, bold=True,
                  align=C if c != 1 else WD_ALIGN_PARAGRAPH.CENTER)

    for r, (num, label, bm, bold) in enumerate(TOC_ENTRIES, start=1):
        for c in range(3):
            cell = table.cell(r, c)
            cell.width = Inches(widths[c])
            clear_cell_borders(cell)
        cell_text(table.cell(r, 0), num, size=12, bold=bold, align=C)
        cell_text(table.cell(r, 1), label, size=12, bold=bold)
        cell = table.cell(r, 2)
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = C
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        pageref(p, bm, size=12, bold=bold)

    para(doc, "Page numbers are live fields. In Word, press Ctrl+A then F9 "
              "and choose “Update entire table” to populate them.",
         size=10, italic=True, align=C, line=1.0, before=10, after=0)


# ===========================================================================
# 1. Introduction
# ===========================================================================
def chapter_1(doc):
    h1(doc, "1. Introduction", bookmark_name="bm_1")

    h2(doc, "1.1  Background", bookmark_name="bm_1_1")
    body(doc, "A typical household now runs a dozen networked appliances — "
              "cameras, door locks, power plugs, lighting, environmental "
              "sensors and voice assistants — that differ enormously in "
              "compute, in traffic volume and in what constitutes normal "
              "behaviour. Because these devices are rarely patched and are "
              "individually weak, the accepted defence is to place an "
              "intelligent monitor on the local gateway rather than on the "
              "devices themselves. That monitor learns the behavioural "
              "signature of each device and raises an alarm when the "
              "signature is violated.")
    body(doc, "Such a monitor cannot be trained once and left alone. Firmware "
              "changes, household routines shift, and devices are added and "
              "removed, so the model must retrain on locally collected "
              "telemetry to remain useful. Continuous retraining at the edge "
              "is therefore not an optional refinement but a requirement of "
              "the deployment. It is also, as this project argues, the point "
              "at which the defence becomes attackable, because anything that "
              "keeps learning can be taught something false.")

    h2(doc, "1.2  Motivation", bookmark_name="bm_1_2")
    body(doc, "Poisoning a model that retrains continuously is attractive "
              "precisely because it is quiet. An attacker does not need to "
              "defeat the detector at the moment of attack; it is sufficient "
              "to contribute training data which shifts the decision boundary "
              "so that, later, hostile traffic falls inside the region the "
              "model considers normal. Nothing alarms at the time of "
              "contribution, and the failure surfaces only when an attack is "
              "missed.")
    body(doc, "The defences available today all answer a variant of the same "
              "question: does this contribution resemble the others? That is "
              "a question about the past, and a competent adversary answers it "
              "by staying close to the crowd. Clean-label poisoning is the "
              "sharpest illustration — no label is altered, so the label "
              "distribution is untouched and every distributional check passes "
              "the contribution without comment. The motivation for this "
              "project is to replace that question with a different one: not "
              "whether an update looks suspicious, but what accepting it would "
              "cost the system's ability to detect tomorrow's attack.")

    h2(doc, "1.3  Scope of the Project", bookmark_name="bm_1_3")
    body(doc, "The project covers a complete, working edge-security pipeline "
              "for a simulated consumer IoT network: device simulation across "
              "six appliance types, an edge gateway, a holographic digital "
              "twin per device, counterfactual future generation, a "
              "multi-class threat detector, a poisoning-attack simulator "
              "covering five strategies, the counterfactual validation gate, a "
              "predictive immunization engine, a quarantine zone with "
              "forensics, gated retraining, and self-healing rollback.")
    body(doc, "The scope is deliberately bounded in three respects. The fleet "
              "is simulated from physically motivated behavioural profiles "
              "rather than captured from hardware, so results demonstrate the "
              "mechanism rather than field performance. The system defends the "
              "training pipeline of an edge detector; it does not address "
              "device firmware integrity, network segmentation or "
              "cryptographic device identity, which are complementary "
              "controls. Finally, comparative benchmarking against "
              "re-implemented reactive baselines is specified in this report "
              "and scheduled for the second phase of the project, so the "
              "results presented here characterise the proposed framework "
              "itself rather than its margin over prior work.")


# ===========================================================================
# 2. Project description and goals
# ===========================================================================
def chapter_2(doc):
    h1(doc, "2. Project Description and Goals", bookmark_name="bm_2")

    # ---------------------------------------------------------------- 2.1 --
    h2(doc, "2.1  Literature Review", bookmark_name="bm_2_1")
    body(doc, "The literature relevant to this project falls into four "
              "strands: the security of digital twins, machine-learning "
              "intrusion detection for IoT, poisoning attacks and their "
              "defences, and counterfactual reasoning. Each strand is mature "
              "in isolation; the gap this project addresses lies at their "
              "intersection.")

    h3(doc, "Security of Digital Twins")
    body(doc, "Alcaraz and Lopez [1] survey the threat landscape of digital "
              "twins across their life cycle and reach a conclusion that "
              "directly shapes this design: the twin is itself a target for "
              "poisoning and spoofing, and trusted state synchronisation is "
              "essential. Their survey characterises the attack surface "
              "thoroughly but proposes no runtime defence, and in the "
              "surveyed literature the twin remains a monitoring or replay "
              "replica rather than a participant in a security decision.")

    h3(doc, "Machine-Learning Intrusion Detection for Consumer IoT")
    body(doc, "Nguyen et al. [4] demonstrate federated self-learning anomaly "
              "detection on a gateway, reporting 95.6 per cent detection of "
              "Mirai-infected devices without labelled attack data. The work "
              "is directly relevant in its device-type-specific modelling, but "
              "it assumes every participating client is honest — which is "
              "precisely the assumption poisoning breaks. Meidan et al. [15] "
              "establish deep autoencoders over network behaviour as an "
              "effective botnet detector, and Antonakakis et al. [14] document "
              "why consumer devices are such attractive targets in the first "
              "place through their analysis of the Mirai botnet.")

    h3(doc, "Poisoning Attacks and Their Defences")
    body(doc, "Tian et al. [2] provide the comprehensive taxonomy of "
              "poisoning attacks and countermeasures, and note explicitly "
              "that the defences surveyed are post-hoc and detection-based, "
              "identifying proactive immunization as an open problem. Biggio "
              "and Roli [13] trace ten years of adversarial machine learning "
              "and frame poisoning as an attack on the training pipeline "
              "rather than on inference. On the attack side, Gu et al. [8] "
              "introduce backdoor triggers that leave overall accuracy "
              "essentially unchanged, which defeats any accuracy-based "
              "promotion gate; Shafahi et al. [7] demonstrate clean-label "
              "poisoning in which no label is altered at all; Tolpegin et al. "
              "[11] and Bagdasaryan et al. [10] transfer both to the "
              "federated setting. On the defence side, Blanchard et al. [9] "
              "propose Byzantine-tolerant aggregation, Fung et al. [12] target "
              "Sybil contributors, and Yang et al. [3] filter malicious client "
              "updates for IoT intrusion detection specifically. Every one of "
              "these defences acts on a contribution after it has been "
              "submitted, and judges it against the current or historical "
              "distribution.")

    h3(doc, "Counterfactual Reasoning and Proactive Robustness")
    body(doc, "Sulem et al. [5] generate diverse counterfactual ensembles to "
              "explain anomalies in time series, showing that counterfactual "
              "alternatives reliably separate genuine anomalies from benign "
              "variation. Their use is explanatory; the counterfactuals never "
              "gate a decision. Madry et al. [6] establish that training on "
              "generated worst-case examples produces durable robustness, "
              "which is the principle this project transfers from test-time "
              "evasion to training-data poisoning. Aggarwal [16] and "
              "Goodfellow et al. [17] provide the underlying treatment of "
              "outlier analysis and of the learning methods employed.")

    para(doc, "Table 2.1  Summary of the reviewed literature",
         size=11, italic=True, align=C, line=1.0, before=10, after=4)
    grid(doc, [
        ["Ref.", "Focus", "Contribution", "Limitation for this problem"],
        ["[1]", "Digital-twin security",
         "Life-cycle threat taxonomy for twins",
         "No runtime defence; twin stays passive"],
        ["[2]", "Poisoning survey",
         "Taxonomy of attacks and defence families",
         "All defences surveyed are post-hoc"],
        ["[3]", "Federated IoT IDS",
         "Filters malicious client updates",
         "Reacts only after submission"],
        ["[4]", "Gateway anomaly detection",
         "Federated self-learning, label-free",
         "Assumes all clients honest"],
        ["[5]", "Counterfactual explanation",
         "Diverse counterfactuals for time series",
         "Explanatory only, never a gate"],
        ["[6]", "Adversarial training",
         "Robustness from generated attacks",
         "Test-time evasion, not poisoning"],
        ["[7]", "Clean-label poisoning",
         "Poisoning with no label alteration",
         "Defeats label-distribution checks"],
        ["[8]", "Backdoor attacks",
         "Triggers that preserve accuracy",
         "Defeats accuracy-based gates"],
        ["[9]-[12]", "Robust aggregation",
         "Byzantine, Sybil and federated defences",
         "Current-state, post-submission"],
    ], widths=[0.75, 1.45, 2.25, 2.45], head_size=10.5, body_size=10)

    # ---------------------------------------------------------------- 2.2 --
    h2(doc, "2.2  Research Gap", bookmark_name="bm_2_2")
    body(doc, "Eight gaps follow from the survey. They are stated in "
              "decreasing order of how directly they motivate the proposed "
              "mechanism.")
    gaps = [
        ("Validation against the current state only.  ",
         "Trust scores, reputation and robust aggregation compare an update "
         "with current or historical observations. None tests it against "
         "where the device is expected to be next, so multi-future "
         "behavioural consistency remains unused as a validation signal."),
        ("Counterfactual reasoning and digital twins are never combined.  ",
         "Counterfactual reasoning has been applied to anomaly explanation "
         "and digital twins to monitoring, but the two have not been joined "
         "into a decision mechanism for validating model updates."),
        ("Attack simulation does not close the loop.  ",
         "Simulation generates an attack, tests the detector and measures "
         "accuracy. It is rarely carried onward to identify the weakness, "
         "synthesise training examples and retrain against them."),
        ("Twins monitor rather than immunize.  ",
         "Digital-twin research targets monitoring, visualisation, fault "
         "prediction and device management. Few approaches use the twin as an "
         "active security environment that predicts behaviour under attack."),
        ("Threat detection remains reactive.  ",
         "Most IoT intrusion detection follows attack, collect, detect, "
         "alert. Predictive detection is seldom integrated with proactive "
         "adaptation of the security model at the edge."),
        ("Poisoning is inadequately addressed in real time.  ",
         "Existing defences identify abnormal samples, aggregate robustly, "
         "filter data or validate statistically — and clean-label poisoning, "
         "which alters no label at all, passes the entire family."),
        ("Edge retraining forces a security–adaptability trade-off.  ",
         "Frequent retraining adapts quickly but widens poisoning exposure, "
         "while infrequent retraining is safer but leaves the detector stale. "
         "Selecting a frequency resolves neither horn; what is missing is a "
         "gate on update content."),
        ("Recovery is manual and total.  ",
         "Detection, quarantine and retraining exist as separate systems. "
         "Restoring a clean model and purging contaminated data is an "
         "operator task, and the usual remedy discards the entire pool."),
    ]
    for lead, text in gaps:
        numbered(doc, text, bold_lead=lead)

    body(doc, "Stated as a single gap: existing IoT security performs "
              "reactive anomaly detection while digital twins are used for "
              "monitoring and prediction; there is limited work integrating "
              "twins with counterfactual future-state simulation to validate "
              "machine-learning updates against multiple plausible future "
              "behaviours, and predictive attack simulation is rarely "
              "connected to secure edge-model retraining. A gap therefore "
              "exists for an integrated framework that uses counterfactual "
              "twin states to validate incoming updates, quarantines "
              "inconsistent updates, and proactively immunizes edge models "
              "against predicted threats.", indent=0.5)

    # ---------------------------------------------------------------- 2.3 --
    h2(doc, "2.3  Objectives", bookmark_name="bm_2_3")
    body(doc, "Seven objectives are defined, each mapped to a research gap "
              "and to a measurable acceptance criterion.")
    para(doc, "Table 2.2  Objectives, mapped gaps and acceptance criteria",
         size=11, italic=True, align=C, line=1.0, before=8, after=4)
    grid(doc, [
        ["#", "Objective", "Gap", "Measurable criterion", "Status"],
        ["O1", "Simulate a heterogeneous consumer IoT fleet and an "
               "on-demand edge gateway.", "G4",
         "Six device types separable on baseline behaviour", "Complete"],
        ["O2", "Build a holographic twin per device across five behavioural "
               "planes.", "G4",
         "Zero false flags on healthy traffic", "Complete"],
        ["O3", "Commit counterfactual futures before the observation they "
               "judge exists.", "G1",
         "20 futures x 5-tick horizon, committed in advance", "Complete"],
        ["O4", "Design a Counterfactual Consistency Score gating every "
               "retraining update.", "G2",
         "Separation between honest and poisoned scores", "Complete"],
        ["O5", "Detect clean-label poisoning that carries no label shift.",
         "G6", "Quarantined at a label shift below 0.10", "Complete"],
        ["O6", "Immunize the detector against synthesised poisoning before "
               "real attacks.", "G3",
         "Poison resistance measured across five strategies", "Complete"],
        ["O7", "Benchmark against reactive baselines across poisoning "
               "rates.", "G1",
         "Attack success rate versus each baseline", "Phase II"],
    ], widths=[0.45, 2.35, 0.55, 2.35, 1.20], head_size=10.5, body_size=10)

    # ---------------------------------------------------------------- 2.4 --
    h2(doc, "2.4  Problem Statement", bookmark_name="bm_2_4")
    body(doc, "An edge-AI threat detector protecting a consumer IoT network "
              "must retrain continuously on locally collected telemetry in "
              "order to remain accurate as the network changes. This creates "
              "an open ingestion path: a contributor — a device, a hub, or a "
              "vendor cloud, any of which may be attacker-controlled — can "
              "submit training data that shifts the model's decision boundary "
              "so that hostile behaviour is later classified as normal.")
    body(doc, "Existing defences evaluate such a contribution only after it "
              "has been submitted and only against the current or historical "
              "state of the network. They are therefore blind to a "
              "contribution that is statistically ordinary but functionally "
              "damaging, and blind entirely to clean-label poisoning, in "
              "which every label is honest.")
    body(doc, "The problem addressed by this project is therefore: given a "
              "candidate retraining update for an edge threat-detection model "
              "in a consumer IoT network, determine before the update is "
              "accepted whether it is consistent with the expected future "
              "behaviour of that specific network, quarantine it if it is "
              "not, and independently harden the model against poisoning "
              "strategies that have not yet been attempted.")

    # ---------------------------------------------------------------- 2.5 --
    h2(doc, "2.5  Project Plan", bookmark_name="bm_2_5")
    body(doc, "The work is organised into two phases across the Fall Semester "
              "2026. Phase I, concluding at Review-2, delivers the complete "
              "implemented framework and its internal measurement. Phase II, "
              "concluding at Review-3, delivers comparative evaluation "
              "against re-implemented reactive baselines, the poisoning-rate "
              "sweep, and dissemination. Figure 1 shows the schedule.")
    figure(doc, FIG / "fig1_gantt.png", "Fig. 1.  Project plan (Gantt chart)")
    body(doc, "Tasks shown in teal are complete and demonstrable; tasks in "
              "amber are planned for Phase II. The dashed marker indicates "
              "the Review-2 checkpoint on 4 September 2026.")


# ===========================================================================
# 3. Technical specification
# ===========================================================================
def chapter_3(doc):
    h1(doc, "3. Technical Specification", bookmark_name="bm_3")

    h2(doc, "3.1  Requirements", bookmark_name="bm_3_1")
    h3(doc, "3.1.1  Functional", bookmark_name="bm_3_1_1")
    frs = [
        ("FR-01  Device simulation.  ",
         "The system shall generate continuous sixteen-feature telemetry for "
         "six consumer device types, each with a distinct behavioural "
         "baseline, and shall deform that telemetry according to a named "
         "attack class on demand."),
        ("FR-02  On-demand ingestion.  ",
         "The gateway shall collect, timestamp and buffer per-device "
         "telemetry only when an operator requests a tick; no collection "
         "shall occur autonomously."),
        ("FR-03  Twin synchronisation.  ",
         "Each device shall have a holographic twin whose five-plane state is "
         "updated from trusted telemetry, and which shall refuse any "
         "observation judged hostile by either detector."),
        ("FR-04  Future commitment.  ",
         "Each ready twin shall commit twenty predicted trajectories over a "
         "five-tick horizon before the observation those trajectories will "
         "be used to judge exists."),
        ("FR-05  Threat detection.  ",
         "The system shall classify normal traffic and six attack classes, "
         "returning a predicted class, a confidence and an operator-facing "
         "risk level for every observation."),
        ("FR-06  Counterfactual validation.  ",
         "Every retraining update shall be scored on six weighted components "
         "against the counterfactual audit bank and judged against a "
         "threshold calibrated from honest updates on the deployed fleet."),
        ("FR-07  Operator control.  ",
         "The system shall apply an accept or quarantine decision only on "
         "explicit operator instruction, shall permit that decision to be "
         "overridden in either direction, and shall record any override."),
        ("FR-08  Quarantine ledger.  ",
         "Quarantined updates shall be retained intact with update "
         "identifier, source, suspected strategy, consistency score and "
         "timestamp, and shall be re-scorable against a later audit bank."),
        ("FR-09  Predictive immunization.  ",
         "The system shall synthesise vaccine rows from committed futures and "
         "shall measure poison resistance by rehearsing five poisoning "
         "strategies against the current training pool."),
        ("FR-10  Guarded promotion and rollback.  ",
         "A retrained candidate shall replace the incumbent only if accuracy, "
         "poison resistance, false-positive rate and pool size all pass their "
         "gates; otherwise the incumbent is retained and remains available "
         "for rollback."),
    ]
    for lead, text in frs:
        bullet(doc, text, bold_lead=lead)

    h3(doc, "3.1.2  Non-Functional", bookmark_name="bm_3_1_2")
    nfrs = [
        ("Performance.  ",
         "Validation of a single update shall complete within one second on "
         "laptop-class CPU hardware; the measured figure is 412 milliseconds."),
        ("Resource economy.  ",
         "The pipeline shall execute without GPU acceleration, so that it "
         "remains deployable on a single-board gateway."),
        ("Determinism.  ",
         "A given random seed shall reproduce an identical end-to-end run, so "
         "that reported results are verifiable."),
        ("Auditability.  ",
         "Every automated decision shall expose the components that produced "
         "it, and every training row shall record its contributing update and "
         "source."),
        ("Fail-safe behaviour.  ",
         "A failed promotion, a failed validation or an internal error shall "
         "leave the incumbent trusted model in service."),
        ("Locality.  ",
         "No telemetry, model or update shall leave the local network during "
         "normal operation."),
        ("Usability.  ",
         "The operator interface shall state, for each stage, what the stage "
         "does before it runs and what its result means afterwards."),
        ("Maintainability.  ",
         "Every tunable constant shall reside in a single configuration "
         "module, and the system shall be covered by an automated test suite."),
    ]
    for lead, text in nfrs:
        bullet(doc, text, bold_lead=lead)

    # ---------------------------------------------------------------- 3.2 --
    h2(doc, "3.2  Feasibility Study", bookmark_name="bm_3_2")

    h3(doc, "3.2.1  Technical Feasibility", bookmark_name="bm_3_2_1")
    body(doc, "The framework is built from established components: a "
              "ridge-regularised vector autoregression for the twin's forward "
              "model, a random-forest classifier for threat detection, and "
              "standard scientific Python libraries throughout. The choice of "
              "a closed-form ridge fit over a recurrent network is deliberate "
              "and is what makes the design feasible on constrained hardware: "
              "the twin must refit repeatedly from a few dozen observations "
              "per device and must produce a distribution of futures rather "
              "than a point estimate, both of which a closed-form fit "
              "provides in microseconds and without a GPU.")
    body(doc, "Technical feasibility is evidenced rather than asserted. The "
              "complete twelve-stage pipeline executes end to end in "
              "approximately fifteen seconds on a laptop-class CPU, and is "
              "covered by sixty-four automated tests. No component requires "
              "specialised hardware, and no stage depends on network "
              "connectivity beyond the local gateway.")

    h3(doc, "3.2.2  Economic Feasibility", bookmark_name="bm_3_2_2")
    body(doc, "Development cost is confined to student effort and "
              "commodity hardware; every library used is open source and "
              "permissively licensed, so licence cost is nil. Because "
              "inference and retraining both execute on the gateway, the "
              "recurring cost of a deployment is the gateway itself — a "
              "single-board computer of the Raspberry Pi class — with no "
              "cloud compute, no data-egress charges and no per-device "
              "subscription.")
    body(doc, "The economic argument for the defence is asymmetric. The "
              "marginal cost of validating an update is a fraction of a "
              "second of CPU time, whereas the cost of a successfully "
              "poisoned detector is the silent loss of protection across the "
              "whole household for as long as the compromise goes unnoticed.")

    h3(doc, "3.2.3  Social Feasibility", bookmark_name="bm_3_2_3")
    body(doc, "Because all processing is local, no household telemetry is "
              "transmitted to a vendor, which addresses the privacy objection "
              "that limits acceptance of monitored home security. The "
              "operator interface is designed so that every automated "
              "judgement is inspectable and can be overruled; a security "
              "control that a human can neither examine nor countermand is an "
              "oracle rather than a control, and is unlikely to be trusted or "
              "retained.")
    body(doc, "Two ethical considerations bound the work. First, the "
              "poisoning simulator exists to test the defence and is confined "
              "to a simulated fleet. Second, an automated system that can "
              "reject a legitimate contribution carries a fairness cost, "
              "which is why the accept threshold is calibrated from honest "
              "traffic rather than fixed, and why quarantine holds an update "
              "intact for re-judgement rather than discarding it.")

    # ---------------------------------------------------------------- 3.3 --
    h2(doc, "3.3  System Specification", bookmark_name="bm_3_3")

    h3(doc, "3.3.1  Hardware Specification", bookmark_name="bm_3_3_1")
    grid(doc, [
        ["Component", "Development specification", "Minimum for deployment"],
        ["Processor", "x86-64, quad core, 2.4 GHz",
         "ARM Cortex-A72 quad core (Raspberry Pi 4 class)"],
        ["Memory", "16 GB", "4 GB"],
        ["Storage", "20 GB free", "8 GB (models, ledger and logs)"],
        ["Graphics", "Not required", "Not required"],
        ["Network", "Local Ethernet or Wi-Fi",
         "Local network only; no internet dependency"],
        ["Display", "1920 x 1080 for the operator console",
         "Any browser-capable client on the LAN"],
    ], widths=[1.35, 2.55, 2.90], head_size=10.5, body_size=10)

    h3(doc, "3.3.2  Software Specification", bookmark_name="bm_3_3_2")
    grid(doc, [
        ["Layer", "Technology", "Role in the system"],
        ["Operating system", "Windows 11 / 64-bit Linux",
         "Development and deployment host"],
        ["Language", "Python 3.11 or later",
         "Simulation, twins, models, validation"],
        ["Numerical", "NumPy",
         "Feature vectors, ridge fit, future roll-out"],
        ["Machine learning", "scikit-learn",
         "Random-forest detector, shadow and probe models"],
        ["Web framework", "FastAPI with Uvicorn",
         "One HTTP endpoint per operator action"],
        ["Front end", "HTML, CSS and vanilla JavaScript",
         "Operator console; no build step required"],
        ["Persistence", "joblib model registry with a JSON ledger",
         "Versioned models and promotion history"],
        ["Testing", "pytest",
         "Sixty-four automated tests across all stages"],
        ["Documentation", "Matplotlib",
         "Generation of the figures in this report"],
    ], widths=[1.45, 2.15, 3.20], head_size=10.5, body_size=10)


# ===========================================================================
# 4. Design approach and details
# ===========================================================================
def chapter_4(doc):
    h1(doc, "4. Design Approach and Details", bookmark_name="bm_4")

    h2(doc, "4.1  System Architecture", bookmark_name="bm_4_1")
    body(doc, "The architecture is a closed loop with three vertical "
              "concerns: a device plane that produces telemetry, an edge "
              "gateway that turns telemetry into judgements, and a decision "
              "and recovery column that acts on those judgements and feeds "
              "the result back into detection. Figure 2 shows the "
              "arrangement.")
    figure(doc, FIG / "fig2_architecture.png",
           "Fig. 2.  System architecture of the proposed framework")

    body(doc, "Telemetry from each simulated device enters the gateway, where "
              "it is collected only on operator request. The holographic twin "
              "layer maintains, for every device, five partial projections of "
              "its behaviour — resource, network, access, topology and "
              "actuation. Modelling the device as separate projections rather "
              "than one combined state vector is what keeps single-plane "
              "attacks visible: a port scan detonates the topology plane and "
              "barely touches resources, while tampered firmware does the "
              "reverse, and averaging the two would hide both.")
    body(doc, "Each ready twin fits a ridge vector autoregression over its "
              "recent history and rolls out twenty future trajectories. Half "
              "are retained as benign futures and half are deformed by each "
              "attack class in the taxonomy, together forming the "
              "counterfactual audit bank. The bank is filtered against the "
              "current trusted detector so that it contains only scenarios "
              "that detector already handles correctly; any subsequent "
              "degradation is then attributable to the update under test and "
              "to nothing else.")
    body(doc, "Live observations are scored against the committed futures and "
              "classified by the threat detector. An incoming retraining "
              "update takes the second path: it is grafted onto a trusted "
              "core, a shadow model is trained, and that shadow model's "
              "behaviour on the audit bank produces the Counterfactual "
              "Consistency Score. Updates clearing the calibrated threshold "
              "join the safe pool; the remainder are quarantined intact. The "
              "immunization engine synthesises vaccine rows from the same "
              "committed futures, secure retraining applies four promotion "
              "gates, and the self-healing controller restores the last "
              "trusted model and purges the offending contributor's rows by "
              "provenance. The promoted model then re-filters the audit bank, "
              "closing the loop.")

    # ---------------------------------------------------------------- 4.2 --
    h2(doc, "4.2  Design", bookmark_name="bm_4_2")

    h3(doc, "4.2.1  Data Flow Diagram", bookmark_name="bm_4_2_1")
    body(doc, "Figure 3 presents the context diagram and its first-level "
              "decomposition. Three external entities interact with the "
              "system: the IoT devices that emit telemetry, the network "
              "operator who drives every stage and receives verdicts, and the "
              "update contributor, which may be attacker-controlled.")
    figure(doc, FIG / "fig3_dfd.png",
           "Fig. 3.  Data flow diagram (Level 0 and Level 1)")
    body(doc, "At Level 1 the framework decomposes into seven processes and "
              "five data stores. Processes 1.0 to 4.0 form the telemetry "
              "path; process 5.0 is the validation gate, drawing audit "
              "scenarios from the future bank (D2) and routing each update "
              "either to the safe pool (D3) or to quarantine (D4). Process "
              "6.0 retrains on validated rows and writes promoted models to "
              "the registry (D5); process 7.0 restores an earlier registry "
              "entry when health degrades.")

    h3(doc, "4.2.2  Use Case Diagram", bookmark_name="bm_4_2_2")
    body(doc, "Figure 4 shows the actors and use cases. The network operator "
              "drives every stage explicitly, which is a design property "
              "rather than an interface convenience: no stage advances "
              "without an instruction, so the boundary between any two stages "
              "can be inspected.")
    figure(doc, FIG / "fig4_usecase.png", "Fig. 4.  Use case diagram")
    body(doc, "The update contributor is modelled as a separate actor and is "
              "explicitly untrusted. Submitting a model update triggers "
              "validation against the committed futures; validation includes "
              "the operator's application of the verdict; and quarantine "
              "analysis extends that flow only when an update has been "
              "held.")

    h3(doc, "4.2.3  Class Diagram", bookmark_name="bm_4_2_3")
    body(doc, "The principal classes and their responsibilities are "
              "summarised in Table 4.1. Each maps to one module of the "
              "implementation.")
    para(doc, "Table 4.1  Principal classes and responsibilities",
         size=11, italic=True, align=C, line=1.0, before=8, after=4)
    grid(doc, [
        ["Class", "Responsibility", "Key operations"],
        ["SimulatedDevice", "Emit telemetry; apply an attack deformation",
         "tick(), start_attack(), stop_attack()"],
        ["IoTFleet", "Own the deployed devices and the labelled corpus",
         "add_device(), collect(), build_corpus()"],
        ["HolographicTwin", "Maintain five-plane state; commit futures; score",
         "observe(), generate_futures(), score()"],
        ["ARPredictor", "Ridge vector autoregression with residual roll-out",
         "fit(), predict_next(), rollout()"],
        ["ThreatDetector", "Multi-class classification of an observation",
         "fit(), predict_proba(), verdict(), evaluate()"],
        ["FutureBank", "Hold labelled counterfactual scenarios",
         "build_bank(), summary()"],
        ["CounterfactualValidator", "Compute the CCS and reach a verdict",
         "calibrate(), validate(), forensics()"],
        ["PoisonForge", "Craft honest and poisoned model updates",
         "clean_update(), craft()"],
        ["QuarantineZone", "Hold, analyse, rescore and release updates",
         "add(), release(), rescore()"],
        ["ImmunizationEngine", "Synthesise vaccines; measure resistance",
         "synthesise(), poison_resistance()"],
        ["SecureRetrainer", "Own the safe pool and the promotion gates",
         "accept(), purge(), retrain()"],
        ["SelfHealingMonitor", "Track health; roll back and purge",
         "record(), check(), heal()"],
    ], widths=[1.85, 2.65, 2.30], head_size=10.5, body_size=9.5)

    h3(doc, "4.2.4  Sequence Diagram", bookmark_name="bm_4_2_4")
    body(doc, "Figure 5 traces the validation of a single retraining update, "
              "which is the sequence that carries the framework's "
              "contribution.")
    figure(doc, FIG / "fig5_sequence.png",
           "Fig. 5.  Sequence diagram for counterfactual update validation")
    body(doc, "The ordering is the mechanism. The twin registry commits its "
              "futures to the bank before the update is submitted, so when "
              "the validator later scores a shadow model against those "
              "scenarios it is conducting a genuine prediction test rather "
              "than fitting an explanation to data already observed. The "
              "verdict returns to the operator as a recommendation; nothing "
              "is applied until the operator applies it, and the operator may "
              "overrule it. After retraining and promotion, the trusted model "
              "re-filters the bank, so the gate sharpens as the model "
              "improves.")


# ===========================================================================
# 9. References
# ===========================================================================
def chapter_9(doc):
    h1(doc, "9. References", bookmark_name="bm_9")

    def ref(n, text):
        p = para(doc, "", size=12, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                 line=1.15, after=6)
        p.paragraph_format.left_indent = Inches(0.4)
        p.paragraph_format.first_line_indent = Inches(-0.4)
        from docx_kit import _style_run
        _style_run(p.add_run(f"[{n}]  "), size=12, bold=True)
        _style_run(p.add_run(text), size=12)

    h2(doc, "Journals")
    ref(1, "C. Alcaraz and J. Lopez, “Digital twin: A comprehensive survey of "
           "security threats,” IEEE Communications Surveys & Tutorials, "
           "vol. 24, no. 3, pp. 1475–1503, 2022.")
    ref(2, "Z. Tian, L. Cui, J. Liang, and S. Yu, “A comprehensive survey on "
           "poisoning attacks and countermeasures in machine learning,” ACM "
           "Computing Surveys, vol. 55, no. 8, pp. 1–35, 2022.")
    ref(3, "R. Yang, H. He, Y. Wang, Y. Qu, and W. Zhang, “Dependable "
           "federated learning for IoT intrusion detection against poisoning "
           "attacks,” Computers & Security, vol. 132, art. no. 103381, 2023.")
    ref(13, "B. Biggio and F. Roli, “Wild patterns: Ten years after the rise "
            "of adversarial machine learning,” Pattern Recognition, vol. 84, "
            "pp. 317–331, 2018.")
    ref(15, "Y. Meidan, M. Bohadana, Y. Mathov, Y. Mirsky, A. Shabtai, "
            "D. Breitenbacher, and Y. Elovici, “N-BaIoT: Network-based "
            "detection of IoT botnet attacks using deep autoencoders,” IEEE "
            "Pervasive Computing, vol. 17, no. 3, pp. 12–22, 2018.")

    h2(doc, "Conference Proceedings")
    ref(4, "T. D. Nguyen, S. Marchal, M. Miettinen, H. Fereidooni, N. Asokan, "
           "and A.-R. Sadeghi, “DÏoT: A federated self-learning anomaly "
           "detection system for IoT,” in Proc. IEEE 39th Int. Conf. "
           "Distributed Computing Systems (ICDCS), Dallas, TX, USA, 2019, "
           "pp. 756–767.")
    ref(6, "A. Madry, A. Makelov, L. Schmidt, D. Tsipras, and A. Vladu, "
           "“Towards deep learning models resistant to adversarial attacks,” "
           "in Proc. Int. Conf. Learning Representations (ICLR), Vancouver, "
           "Canada, 2018.")
    ref(7, "A. Shafahi, W. R. Huang, M. Najibi, O. Suciu, C. Studer, "
           "T. Dumitras, and T. Goldstein, “Poison frogs! Targeted "
           "clean-label poisoning attacks on neural networks,” in Advances in "
           "Neural Information Processing Systems (NeurIPS), 2018.")
    ref(9, "P. Blanchard, E. M. El Mhamdi, R. Guerraoui, and J. Stainer, "
           "“Machine learning with adversaries: Byzantine tolerant gradient "
           "descent,” in Advances in Neural Information Processing Systems "
           "(NeurIPS), 2017.")
    ref(10, "E. Bagdasaryan, A. Veit, Y. Hua, D. Estrin, and V. Shmatikov, "
            "“How to backdoor federated learning,” in Proc. 23rd Int. Conf. "
            "Artificial Intelligence and Statistics (AISTATS), 2020, "
            "pp. 2938–2948.")
    ref(11, "V. Tolpegin, S. Truex, M. E. Gursoy, and L. Liu, “Data poisoning "
            "attacks against federated learning systems,” in Proc. European "
            "Symp. Research in Computer Security (ESORICS), 2020, "
            "pp. 480–501.")
    ref(12, "C. Fung, C. J. M. Yoon, and I. Beschastnikh, “The limitations of "
            "federated learning in Sybil settings,” in Proc. 23rd Int. Symp. "
            "Research in Attacks, Intrusions and Defenses (RAID), 2020, "
            "pp. 301–316.")
    ref(14, "M. Antonakakis et al., “Understanding the Mirai botnet,” in "
            "Proc. 26th USENIX Security Symposium, Vancouver, Canada, 2017, "
            "pp. 1093–1110.")

    h2(doc, "Preprints")
    ref(5, "D. Sulem, M. Donini, M. B. Zafar, F.-X. Aubet, J. Gasthaus, "
           "T. Januschowski, S. Das, K. Kenthapadi, and C. Archambeau, "
           "“Diverse counterfactual explanations for anomaly detection in "
           "time series,” arXiv:2203.11103, 2022.")
    ref(8, "T. Gu, B. Dolan-Gavitt, and S. Garg, “BadNets: Identifying "
           "vulnerabilities in the machine learning model supply chain,” "
           "arXiv:1708.06733, 2017.")

    h2(doc, "Books")
    ref(16, "C. C. Aggarwal, Outlier Analysis, 2nd ed. Cham, Switzerland: "
            "Springer, 2017.")
    ref(17, "I. Goodfellow, Y. Bengio, and A. Courville, Deep Learning. "
            "Cambridge, MA, USA: MIT Press, 2016.")

    h2(doc, "Web References")
    ref(18, "OWASP Internet of Things Project. [Online]. Available: "
            "https://owasp.org/www-project-internet-of-things/")
    ref(19, "scikit-learn: Machine Learning in Python. [Online]. Available: "
            "https://scikit-learn.org/stable/")
    ref(20, "FastAPI Documentation. [Online]. Available: "
            "https://fastapi.tiangolo.com/")


# ===========================================================================
# Assembly
# ===========================================================================


# The front lists. Page numbers stay blank so they can be filled after the
# first print run, exactly as the template's own placeholders show.
FIGURES = [
    ("2.1", "Project plan and milestone schedule", ""),
    ("4.1", "System architecture of the proposed framework", ""),
    ("4.2", "Data flow diagram", ""),
    ("4.3", "Use case diagram", ""),
    ("4.4", "Sequence diagram of a validation cycle", ""),
]

TABLES = [
    ("5.1", "Module responsibilities", ""),
    ("5.2", "The six components of the Counterfactual Consistency Score", ""),
    ("5.3", "Test coverage by area", ""),
    ("7.1", "Edge detector performance on held-out evaluation data", ""),
    ("7.2", "Validation decisions, 13 of 13 correct", ""),
    ("7.3", "Live hardware compared with the simulated fleet", ""),
]

SYMBOLS = [
    ("z", "Standard-deviation multiplier used to place the accept threshold "
          "below the honest mean"),
    ("σ", "Standard deviation of the honest Counterfactual Consistency "
               "Scores"),
    ("α", "Smoothing factor of the twin's exponentially weighted moving "
               "average"),
    ("w", "Weight of a component within the Counterfactual Consistency "
          "Score"),
    ("H", "Prediction horizon, in ticks, of a committed future"),
    ("N", "Number of counterfactual futures committed per twin"),
    ("λ", "Ridge regularisation coefficient of the forward model"),
]

ABBREVIATIONS = [
    ("API", "Application Programming Interface"),
    ("AR", "Autoregressive"),
    ("CCS", "Counterfactual Consistency Score"),
    ("CPU", "Central Processing Unit"),
    ("CSV", "Comma-Separated Values"),
    ("DDoS", "Distributed Denial of Service"),
    ("DFD", "Data Flow Diagram"),
    ("EWMA", "Exponentially Weighted Moving Average"),
    ("FNR", "False Negative Rate"),
    ("FPR", "False Positive Rate"),
    ("HTTP", "Hypertext Transfer Protocol"),
    ("IoT", "Internet of Things"),
    ("JSON", "JavaScript Object Notation"),
    ("MAD", "Median Absolute Deviation"),
    ("ML", "Machine Learning"),
    ("MPA", "Multi-Page Application"),
    ("PBKDF2", "Password-Based Key Derivation Function 2"),
    ("PnP", "Plug and Play"),
    ("PRG", "Post/Redirect/Get"),
    ("SQL", "Structured Query Language"),
    ("USB", "Universal Serial Bus"),
    ("UVC", "USB Video Class"),
    ("VAR", "Vector Autoregression"),
    ("WAL", "Write-Ahead Logging"),
    ("WMI", "Windows Management Instrumentation"),
]

def set_properties(doc) -> None:
    """Authorship on the file itself, not the library's defaults."""
    props = doc.core_properties
    props.author = TEAM[1][1].title()          # the submitting candidate
    props.last_modified_by = props.author
    props.title = TITLE.title()
    props.subject = "BCSE497J Project-I"
    props.comments = ""
    props.category = ""
    props.keywords = ""


def main() -> int:
    doc = Document()
    set_properties(doc)

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)

    for section in doc.sections:
        section.page_width = Inches(8.27)      # A4
        section.page_height = Inches(11.69)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.25)
        section.right_margin = Inches(1.0)

    # Section 1 - cover and the signed pages, unnumbered
    fm.cover(doc, title=TITLE, team=TEAM, guide=GUIDE,
             guide_designation=GUIDE_DESIGNATION, school=SCHOOL,
             month=MONTH)
    fm.declaration(doc, title=TITLE, team=TEAM, guide=GUIDE, school=SCHOOL)
    fm.certificate(doc, title=TITLE, team=TEAM, guide=GUIDE,
                   guide_designation=GUIDE_DESIGNATION, school=SCHOOL)
    page_numbering(doc.sections[0], "decimal", 1, show=False)

    # Section 2 - front matter, lower-case roman
    front = new_section(doc)
    front.page_width, front.page_height = Inches(8.27), Inches(11.69)
    front.top_margin = front.bottom_margin = Inches(1.0)
    front.left_margin, front.right_margin = Inches(1.25), Inches(1.0)
    # The template's own order: the lists come after the contents, and the
    # abstract is the last page of the front matter, immediately before
    # Chapter 1 -- not the first.
    fm.acknowledgements(doc, guide=GUIDE, team=TEAM)
    table_of_contents(doc)
    fm.list_of_figures(doc, FIGURES)
    fm.list_of_tables(doc, TABLES)
    fm.list_of_abbreviations(doc, ABBREVIATIONS)
    fm.symbols_and_notations(doc, SYMBOLS)
    abstract(doc)
    page_numbering(front, "lowerRoman", 1)

    # Section 3 - body, arabic restarting at 1
    main_body = new_section(doc)
    main_body.page_width, main_body.page_height = Inches(8.27), Inches(11.69)
    main_body.top_margin = main_body.bottom_margin = Inches(1.0)
    main_body.left_margin, main_body.right_margin = Inches(1.25), Inches(1.0)
    page_numbering(main_body, "decimal", 1)

    chapter_1(doc)
    chapter_2(doc)
    chapter_3(doc)
    chapter_4(doc)
    chapter_5(doc)
    chapter_6(doc)
    chapter_7(doc)
    chapter_8(doc)
    chapter_9(doc)
    appendix_a(doc)

    doc.save(OUT)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
