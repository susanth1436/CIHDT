"""Review-2 deck, slide 7: the research gap.

Eight gaps as supplied, laid out four across and two down, each bound to the
mechanism in this framework that answers it.  The closing band carries the
single-paragraph answer to "what exactly is your research gap?", because that
is the question a panel actually asks.

Copy is kept short on purpose: at Times New Roman these cards are the densest
thing in the deck, and a gap nobody can read from the back of the room is not
a gap that has been communicated.
"""
from __future__ import annotations

from build_review2 import (CARD, NAVY, RULE, SLATE, TEAL, WHITE, bar, box,
                           chip, frame, rich, takeaway, tb, write)

# Four columns across the 11.95 in content width, two rows deep.
COL_W, COL_GAP = 2.84, 0.1967
ROW_Y = (1.64, 3.94)
CARD_H = 2.22

GAPS = [
    ("G1", "Twins Monitor, They Do Not Immunize",
     "Twin research targets monitoring, visualisation and fault prediction. "
     "Few use the twin as an active security environment.",
     "Futures drive the security decision"),

    ("G2", "Threat Detection Is Reactive",
     "Detection runs attack, collect, detect, alert. It is rarely joined to "
     "proactive adaptation of the model at the edge.",
     "Prepare the model before the attack"),

    ("G3", "Poisoning Unaddressed In Real Time",
     "Defences identify abnormal samples, aggregate robustly or validate "
     "statistically — always after the update is submitted.",
     "Test the update against future behaviour"),

    ("G4", "Counterfactuals And Twins Stay Separate",
     "Counterfactual reasoning and twin modelling have been explored "
     "independently, never joined into a security decision.",
     "Counterfactuals + twins + IoT security"),

    ("G5", "Validation Against Current State Only",
     "Anomaly detection compares behaviour with current or historical "
     "normal. Multi-future consistency is barely considered.",
     "Compare against 20 committed futures"),

    ("G6", "Security–Adaptability Trade-Off",
     "Frequent retraining adapts fast but widens exposure; infrequent "
     "retraining is safer but stale. Frequency resolves neither.",
     "Gate on content, not on frequency"),

    ("G7", "Simulation Stops At Measurement",
     "Simulation generates an attack, tests the detector and measures "
     "accuracy. It rarely feeds onward into retraining.",
     "Simulate, immunize, then re-test"),

    ("G8", "Components Operate Independently",
     "Detection, quarantine and retraining are separate systems, with no "
     "closed loop uniting twin, validation and rollback.",
     "One closed-loop, self-adaptive design"),
]


def slide_gap(prs):
    s = frame(prs, 5, "Gap Analysis", "Research Gap",
              "Eight gaps drawn from the survey  ·  each bound to the "
              "mechanism in this framework that answers it", 7)

    for i, (tag, head, body, fix) in enumerate(GAPS):
        col, row = i % 4, i // 4
        x = 0.69 + col * (COL_W + COL_GAP)
        y = ROW_Y[row]

        box(s, x, y, COL_W, CARD_H, fill=WHITE, border=RULE)
        bar(s, x, y, COL_W, 0.04, TEAL)
        chip(s, x + 0.14, y + 0.14, 0.56, tag, color=WHITE, fill=NAVY,
             size=10.5, h=0.24)
        t = tb(s, x + 0.78, y + 0.12, COL_W - 0.92, 0.42)
        write(t, head, size=12, bold=True, color=NAVY, line=0.94)
        t = tb(s, x + 0.14, y + 0.60, COL_W - 0.28, 0.98)
        write(t, body, size=10.5, color=SLATE, line=1.04)

        box(s, x + 0.14, y + 1.62, COL_W - 0.28, 0.50, fill=CARD, border=None)
        t = tb(s, x + 0.26, y + 1.70, COL_W - 0.48, 0.40)
        rich(t, [("→  ", {"size": 10.5, "bold": True, "color": TEAL}),
                 (fix, {"size": 10.5, "bold": True, "color": NAVY})],
             line=1.02)

    takeaway(s, "Stated as one gap:",
             "no work validates a model update against multiple plausible "
             "future states, nor closes simulated attacks back into secure "
             "edge retraining.",
             y=6.26, h=0.68, size=14)
