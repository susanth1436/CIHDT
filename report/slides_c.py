"""Review-2 deck, slides 12-15: evaluation, results, synthesis, references."""
from __future__ import annotations

from pptx.enum.text import PP_ALIGN

from build_review2 import (AMBER, CARD, INK, NAVY, RED, RULE, SLATE, TEAL,
                           WHITE, bar, box, chip, frame, grid_table, rich,
                           takeaway, tb, write)


# ===========================================================================
# SLIDE 12 - experimental design
# ===========================================================================
def slide_experiments(prs):
    s = frame(prs, 10, "Evaluation", "Experiments — Design",
              "Testbed, attack model, baselines and metrics  ·  what is "
              "measured and what is still outstanding", 13)

    panels = [
        ("EXPERIMENTAL SETUP",
         ["Eight simulated devices — two cameras, two bulbs, plug, lock, "
          "temperature sensor, speaker.",
          "Telemetry: 16 features per device per tick, clamped to physical "
          "ranges; counts rounded to integers.",
          "Corpus: 2,660 rows balanced across seven classes, attacks drawn "
          "across intensities 0.28–1.0.",
          "Split: 1,649 train, 1,011 held-out evaluation, 1,100 trusted "
          "core for shadow models.",
          "Runs on a laptop-class CPU; no GPU anywhere in the pipeline."]),
        ("ATTACK MODEL",
         ["Runtime attacks: DDoS, botnet C2, brute force, port scan, data "
          "exfiltration, firmware tamper.",
          "Poisoning strategies: label flipping, gradual poisoning, backdoor "
          "trigger, Sybil flood, clean-label.",
          "Each poisoned update is weighted to a 35% federated share of "
          "training mass, the realistic contributor scale.",
          "Ground truth is recorded by the simulator but never shown to the "
          "twin, the detector or the validator."]),
    ]
    for i, (head, items) in enumerate(panels):
        x = 0.69 + i * 6.13
        box(s, x, 1.62, 5.82, 2.42, fill=WHITE, border=RULE)
        bar(s, x, 1.62, 5.82, 0.04, TEAL)
        t = tb(s, x + 0.18, 1.76, 5.46, 0.22)
        write(t, head, size=12, bold=True, color=TEAL)
        for j, item in enumerate(items):
            t = tb(s, x + 0.18, 2.06 + j * 0.38, 5.46, 0.36)
            rich(t, [("—  ", {"size": 12, "bold": True, "color": RULE}),
                     (item, {"size": 12, "color": NAVY})], line=1.03)

    box(s, 0.69, 4.16, 5.82, 2.06, fill=WHITE, border=RULE)
    bar(s, 0.69, 4.16, 5.82, 0.04, TEAL)
    t = tb(s, 0.87, 4.30, 5.46, 0.22)
    write(t, "EVALUATION METRICS", size=12, bold=True, color=TEAL)
    metrics = [
        ("Detection", "accuracy, macro-F1, false positive and false "
                      "negative rate"),
        ("Twin", "counterfactual consistency separation, flag rate on "
                 "healthy traffic"),
        ("Validation", "CCS separation between honest and poisoned updates; "
                       "decision correctness"),
        ("Immunization", "surviving attack recall per rehearsed strategy"),
        ("Cost", "per-update validation latency at the edge"),
    ]
    for j, (k, v) in enumerate(metrics):
        t = tb(s, 0.87, 4.60 + j * 0.32, 5.46, 0.30)
        rich(t, [(k + "  ", {"size": 12, "bold": True, "color": NAVY}),
                 (v, {"size": 12, "color": SLATE})], line=1.0)

    box(s, 6.82, 4.16, 5.82, 2.06, fill=CARD, border=RULE)
    bar(s, 6.82, 4.16, 5.82, 0.04, AMBER)
    t = tb(s, 7.00, 4.30, 5.46, 0.22)
    write(t, "OUTSTANDING FOR REVIEW-3", size=12, bold=True, color=AMBER)
    todo = [
        "Re-implement the three reactive baselines — no defence, "
        "statistical anomaly filtering, robust aggregation / trust scoring.",
        "Sweep poisoning rates at 5%, 10%, 20% and 30% rather than a single "
        "federated share.",
        "Measure attack success rate and recovery time after rollback "
        "against each baseline.",
        "Cross-check the twin on a public IoT capture to test whether the "
        "simulated baselines transfer.",
    ]
    for j, item in enumerate(todo):
        t = tb(s, 7.00, 4.60 + j * 0.40, 5.46, 0.38)
        rich(t, [("○  ", {"size": 12, "bold": True, "color": AMBER}),
                 (item, {"size": 12, "color": NAVY})], line=1.03)

    takeaway(s, "Stated plainly:",
             "the framework's own numbers are measured end to end; the "
             "comparison against reactive baselines is designed but not yet "
             "run, and is the main Review-3 deliverable.")


# ===========================================================================
# SLIDE 13 - results
# ===========================================================================
def slide_results(prs):
    s = frame(prs, 10, "Evaluation", "Experiments — Measured Results",
              "Eight-device fleet, seed 1337  ·  reproducible end to end "
              "in roughly fifteen seconds", 14)

    # headline metrics
    heads = [("95.7%", "DETECTION ACCURACY", "macro-F1 0.956", TEAL),
             ("3.1%", "FALSE NEGATIVES", "attacks called benign", TEAL),
             ("4.9%", "FALSE POSITIVES", "benign called attack", TEAL),
             ("13 / 13", "CORRECT DECISIONS", "accept vs quarantine", TEAL),
             ("5 / 5", "STRATEGIES NAMED", "correct attribution", TEAL)]
    for i, (val, label, sub, colour) in enumerate(heads):
        x = 0.69 + i * 2.42
        box(s, x, 1.60, 2.28, 0.92, fill=WHITE, border=RULE)
        bar(s, x, 1.60, 2.28, 0.045, colour)
        t = tb(s, x + 0.14, 1.72, 2.00, 0.34)
        write(t, val, size=23, bold=True, color=INK)
        t = tb(s, x + 0.14, 2.08, 2.00, 0.20)
        write(t, label, size=10, bold=True, color=colour)
        t = tb(s, x + 0.14, 2.27, 2.00, 0.20)
        write(t, sub, size=10, color=SLATE)

    # CCS table
    t = tb(s, 0.69, 2.68, 6.00, 0.22)
    write(t, "COUNTERFACTUAL VALIDATION  ·  GATE CALIBRATED AT 0.857",
          size=12, bold=True, color=TEAL)
    rows = [
        ["Update crafted as", "CCS", "Decision", "Attributed as", "Correct"],
        ["Honest contribution", "0.910", ("ACCEPTED", TEAL),
         "clean", "Yes"],
        ["Label flipping", "0.625", ("QUARANTINED", RED),
         "label_flip", "Yes"],
        ["Gradual poisoning", "0.801", ("QUARANTINED", RED),
         "gradual_poisoning", "Yes"],
        ["Backdoor trigger", "0.666", ("QUARANTINED", RED),
         "backdoor", "Yes"],
        ["Sybil flood (8 shards)", "0.673–0.730", ("QUARANTINED", RED),
         "sybil", "Yes"],
        ["Clean-label poisoning", "0.734", ("QUARANTINED", RED),
         "clean_label", "Yes"],
    ]
    grid_table(s, 0.69, 2.94, 6.34, rows, [2.10, 1.10, 1.35, 1.55, 0.70],
               header_h=0.32, row_h=0.36, head_size=11, body_size=10.5)

    # right column
    t = tb(s, 7.34, 2.68, 5.30, 0.22)
    write(t, "POISON RESISTANCE  ·  REHEARSED PER STRATEGY", size=12,
          bold=True, color=TEAL)
    res = [("Label flipping", "97.2%"), ("Gradual poisoning", "100.0%"),
           ("Backdoor trigger", "97.2%"), ("Sybil flood", "99.1%"),
           ("Clean-label", "94.3%")]
    for i, (k, v) in enumerate(res):
        y = 2.96 + i * 0.34
        box(s, 7.34, y, 5.30, 0.30, fill=WHITE if i % 2 == 0 else CARD,
            border=RULE, radius=False, line_w=0.5)
        t = tb(s, 7.46, y + 0.04, 3.20, 0.24)
        write(t, k, size=10.5, color=NAVY)
        bar(s, 10.70, y + 0.11, 1.40 * float(v.rstrip("%")) / 100, 0.10, TEAL)
        t = tb(s, 12.16, y + 0.03, 0.40, 0.24, align=PP_ALIGN.RIGHT)
        write(t, v, size=10.5, bold=True, color=NAVY)
    t = tb(s, 7.34, 4.70, 5.30, 0.24)
    rich(t, [("Overall 0.976", {"size": 12, "bold": True, "color": NAVY}),
             ("   against a promotion gate of 0.78; weakest against "
              "clean-label.", {"size": 12, "color": SLATE})])

    # twin separation
    t = tb(s, 0.69, 5.46, 6.00, 0.22)
    write(t, "TWIN CONSISTENCY SEPARATION", size=12, bold=True, color=TEAL)
    box(s, 0.69, 5.70, 6.34, 0.56, fill=WHITE, border=RULE)
    t = tb(s, 0.87, 5.78, 6.00, 0.42)
    write(t, "Never below 0.358 on healthy traffic against a 0.35 flag "
             "threshold — zero false alarms; attacks collapsed to 0.000.",
          size=12, color=NAVY, line=1.08)

    box(s, 7.34, 5.06, 5.30, 1.20, fill=CARD, border=RULE)
    t = tb(s, 7.52, 5.16, 4.94, 0.22)
    write(t, "COST AND REPRODUCIBILITY", size=11.5, bold=True, color=TEAL)
    for i, (k, v) in enumerate([("Validation latency", "412 ms per update"),
                                ("Full pipeline run", "≈15 s, CPU only"),
                                ("Automated tests", "64 passing")]):
        t = tb(s, 7.52, 5.44 + i * 0.26, 4.94, 0.24)
        rich(t, [(k + "   ", {"size": 11.5, "bold": True, "color": NAVY}),
                 (v, {"size": 11.5, "color": SLATE})])

    takeaway(s, "The decisive case:",
             "clean-label poisoning carries a label shift below 0.10 and is "
             "invisible to every distributional check — it was still "
             "quarantined, on the label-agreement component alone.")


# ===========================================================================
# SLIDE 14 - synthesis
# ===========================================================================
def slide_synthesis(prs):
    s = frame(prs, 11, "Synthesis", "Novelty and Conclusion",
              "What is genuinely new, and what remains before Review-3", 15)

    t = tb(s, 0.69, 1.60, 6.00, 0.22)
    write(t, "THREE NOVEL CONTRIBUTIONS", size=12, bold=True, color=TEAL)
    contribs = [
        ("01", "Counterfactual Validation",
         "A retraining update is judged by what it would cost against futures "
         "the twin committed to before the update existed — not by whether "
         "it resembles past traffic. Half the audit bank is attack-"
         "conditioned, so the question asked is whether tomorrow's attack "
         "would still be caught."),
        ("02", "Predictive Immunization",
         "Vaccines are synthesised from that fleet's own committed futures "
         "and folded into retraining before any real attack. The trigger "
         "vaccine deliberately does not use the attacker's trigger — it "
         "teaches that pinning arbitrary constants does not make a row "
         "benign."),
        ("03", "Twin-Assisted Security Decisions",
         "The twin participates in the accept/quarantine decision rather than "
         "mirroring the device, and defends itself: any observation either "
         "detector distrusts is refused entry to the twin's own history."),
    ]
    for i, (num, head, body) in enumerate(contribs):
        y = 1.86 + i * 1.46
        box(s, 0.69, y, 6.34, 1.34, fill=WHITE, border=RULE)
        chip(s, 0.85, y + 0.14, 0.42, num, color=WHITE, fill=TEAL, size=11.5,
             h=0.26)
        t = tb(s, 1.37, y + 0.11, 5.50, 0.28)
        write(t, head, size=14.5, bold=True, color=NAVY)
        t = tb(s, 0.85, y + 0.46, 6.02, 0.82)
        write(t, body, size=12, color=SLATE, line=1.08)

    t = tb(s, 7.34, 1.60, 5.30, 0.22)
    write(t, "ONE-LINE NOVELTY STATEMENT", size=12, bold=True, color=TEAL)
    box(s, 7.34, 1.86, 5.30, 1.10, fill=CARD, border=RULE)
    bar(s, 7.34, 1.86, 0.05, 1.10, TEAL)
    t = tb(s, 7.56, 1.98, 5.00, 0.90)
    write(t, "Using a digital twin's set of plausible future states as a "
             "counterfactual security test before accepting an AI model "
             "update, followed by predictive immunization of the edge model "
             "against simulated future attacks.",
          size=13, italic=True, color=NAVY, line=1.10)

    t = tb(s, 7.34, 3.10, 5.30, 0.22)
    write(t, "CONCLUSION", size=12, bold=True, color=TEAL)
    concl = [
        "Poisoning is prevented at the gate rather than repaired after the "
        "model has already been damaged.",
        "The defence is fleet-adaptive: the accept threshold is calibrated "
        "from honest traffic on the deployed network, not hard-coded.",
        "Every decision is inspectable and overridable — a security "
        "control an operator cannot countermand is an oracle, not a control.",
    ]
    for i, c in enumerate(concl):
        t = tb(s, 7.34, 3.38 + i * 0.60, 5.30, 0.56)
        rich(t, [("—  ", {"size": 12, "bold": True, "color": RULE}),
                 (c, {"size": 12, "color": NAVY})], line=1.06)

    box(s, 7.34, 5.20, 5.30, 1.02, fill=CARD, border=RULE)
    bar(s, 7.34, 5.20, 5.30, 0.04, AMBER)
    t = tb(s, 7.52, 5.34, 4.94, 0.22)
    write(t, "NEXT STEPS TO REVIEW-3", size=11.5, bold=True, color=AMBER)
    t = tb(s, 7.52, 5.58, 4.94, 0.58)
    write(t, "Benchmark against the three reactive baselines, run the "
             "poisoning-rate sweep, and prepare the patent filing on the "
             "counterfactual validation mechanism.",
          size=11.5, color=NAVY, line=1.06)

    takeaway(s, "Positioning:",
             "digital twins, AI threat detection and poisoning defence are "
             "each well studied — the contribution is the security "
             "decision mechanism that combines them.")


# ===========================================================================
# SLIDE 15 - references
# ===========================================================================
def slide_references(prs):
    s = frame(prs, 12, "Bibliography", "References",
              "IEEE format  ·  verify every volume, issue and page range "
              "against the publisher before submission", 16)

    refs = [
        "C. Alcaraz and J. Lopez, “Digital twin: A comprehensive survey of "
        "security threats,” IEEE Communications Surveys & Tutorials, vol. 24, "
        "no. 3, pp. 1475–1503, 2022.",
        "Z. Tian, L. Cui, J. Liang, and S. Yu, “A comprehensive survey on "
        "poisoning attacks and countermeasures in machine learning,” ACM "
        "Computing Surveys, vol. 55, no. 8, pp. 1–35, 2022.",
        "R. Yang, H. He, Y. Wang, Y. Qu, and W. Zhang, “Dependable federated "
        "learning for IoT intrusion detection against poisoning attacks,” "
        "Computers & Security, vol. 132, art. no. 103381, 2023.",
        "T. D. Nguyen et al., “DÏoT: A federated self-learning anomaly "
        "detection system for IoT,” in Proc. IEEE Int. Conf. Distributed "
        "Computing Systems (ICDCS), 2019, pp. 756–767.",
        "D. Sulem et al., “Diverse counterfactual explanations for anomaly "
        "detection in time series,” arXiv:2203.11103, 2022.",
        "A. Madry, A. Makelov, L. Schmidt, D. Tsipras, and A. Vladu, “Towards "
        "deep learning models resistant to adversarial attacks,” in Proc. "
        "Int. Conf. Learning Representations (ICLR), Vancouver, Canada, 2018.",
        "A. Shafahi et al., “Poison frogs! Targeted clean-label poisoning "
        "attacks on neural networks,” in Advances in Neural Information "
        "Processing Systems (NeurIPS), 2018.",
        "T. Gu, B. Dolan-Gavitt, and S. Garg, “BadNets: Identifying "
        "vulnerabilities in the machine learning model supply chain,” "
        "arXiv:1708.06733, 2017.",
        "P. Blanchard et al., “Machine learning with adversaries: Byzantine "
        "tolerant gradient descent,” in Advances in Neural Information "
        "Processing Systems (NeurIPS), 2017.",
        "E. Bagdasaryan et al., “How to backdoor federated learning,” in "
        "Proc. Int. Conf. Artificial Intelligence and Statistics "
        "(AISTATS), 2020, pp. 2938–2948.",
        "V. Tolpegin, S. Truex, M. E. Gursoy, and L. Liu, “Data poisoning "
        "attacks against federated learning systems,” in Proc. European Symp. "
        "Research in Computer Security (ESORICS), 2020, pp. 480–501.",
        "C. Fung, C. J. M. Yoon, and I. Beschastnikh, “The limitations of "
        "federated learning in Sybil settings,” in Proc. 23rd Int. Symp. "
        "Research in Attacks, Intrusions and Defenses (RAID), 2020, "
        "pp. 301–316.",
        "B. Biggio and F. Roli, “Wild patterns: Ten years after the rise of "
        "adversarial machine learning,” Pattern Recognition, vol. 84, "
        "pp. 317–331, 2018.",
        "M. Antonakakis et al., “Understanding the Mirai botnet,” in Proc. "
        "26th USENIX Security Symposium, Vancouver, Canada, 2017, "
        "pp. 1093–1110.",
        "Y. Meidan et al., “N-BaIoT: Network-based detection of IoT botnet "
        "attacks using deep autoencoders,” IEEE Pervasive Computing, "
        "vol. 17, no. 3, pp. 12–22, 2018.",
    ]
    for i, ref in enumerate(refs):
        col, row = i % 2, i // 2
        x = 0.69 + col * 6.13
        y = 1.62 + row * 0.60
        t = tb(s, x, y, 5.82, 0.56)
        rich(t, [(f"[{i + 1}]  ", {"size": 11, "bold": True, "color": TEAL}),
                 (ref, {"size": 11, "color": NAVY})], line=1.04)

    takeaway(s, "Before submission:",
             "references [7] to [15] were added for Review-2 and their page "
             "ranges have not yet been checked against the publisher record "
             "— verify each one, then delete this note.")
