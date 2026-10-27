"""Review-2 deck, slide 10: the block diagram.

Slide 9 shows the system as layers.  This slide shows it as a *flow* — the
path a piece of telemetry and a retraining update each take, the point at
which they meet, the fork, and the loop that closes back on itself.  Every
connector here is a real shape, so the diagram survives being read from the
back of a room.
"""
from __future__ import annotations

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from build_review2 import (AMBER, CARD, INK, NAVY, RED, RULE, SLATE, TEAL,
                           WHITE, bar, box, chip, frame, rich, takeaway, tb,
                           write)

# --- geometry --------------------------------------------------------------
COL_X = [0.69, 3.74, 6.79, 9.84]      # four-column grid
COL_W = 2.80
ROW1_Y, ROW2_Y, BOX_H = 1.64, 2.96, 0.84
BUS_Y = 3.98                          # the distribution bar under the gate
ROW3_Y, ROW3_H = 4.28, 0.84
ROW4_Y, ROW4_H = 5.40, 0.62
LOOP_X = 12.82                        # feedback return runs down this margin


def arrow(slide, x, y, w, h, direction, *, color=TEAL):
    """A real arrow shape, so connectors survive projection."""
    shape = slide.shapes.add_shape(
        {"right": MSO_SHAPE.RIGHT_ARROW, "left": MSO_SHAPE.LEFT_ARROW,
         "down": MSO_SHAPE.DOWN_ARROW, "up": MSO_SHAPE.UP_ARROW}[direction],
        Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def run(slide, x, y, w, h, *, color=TEAL):
    """A plain connector run, for the long feedback path."""
    return bar(slide, x, y, w, h, color)


def node(slide, x, y, w, h, tag, head, sub, *, fill=WHITE, accent=TEAL,
         head_size=13, sub_size=10.5):
    """One labelled block in the diagram."""
    box(slide, x, y, w, h, fill=fill, border=RULE)
    bar(slide, x, y, w, 0.04, accent)
    if tag:
        chip(slide, x + 0.12, y + 0.12, 0.42, tag, color=WHITE, fill=NAVY,
             size=10, h=0.22)
        tx, tw = x + 0.62, w - 0.74
    else:
        tx, tw = x + 0.14, w - 0.28
    t = tb(slide, tx, y + 0.11, tw, 0.26)
    write(t, head, size=head_size, bold=True, color=NAVY)
    t = tb(slide, x + 0.14, y + 0.40, w - 0.28, h - 0.48)
    write(t, sub, size=sub_size, color=SLATE, line=1.04)


def slide_blockdiagram(prs):
    s = frame(prs, 7, "System Design", "Block Diagram — The Validation Loop",
              "Two inbound paths, one decision point, and a loop that closes "
              "back on the audit bank", 10)

    # ---------------------------------------------------------- row 1 ------
    t = tb(s, 0.69, 1.42, 5.00, 0.20)
    write(t, "TELEMETRY PATH", size=11, bold=True, color=TEAL)

    row1 = [
        ("", "IoT Fleet",
         "six consumer device types  ·  16 telemetry features per tick"),
        ("M1", "Edge Gateway",
         "collects only when asked  ·  nothing leaves the local network"),
        ("M2", "Holographic Twins",
         "five behavioural planes  ·  hostile observations refused entry"),
        ("M3", "Counterfactual Audit Bank",
         "20 futures x 5 ticks  ·  half benign, half attack-conditioned"),
    ]
    for i, (tag, head, sub) in enumerate(row1):
        node(s, COL_X[i], ROW1_Y, COL_W, BOX_H, tag, head, sub)
        if i < 3:
            arrow(s, COL_X[i] + COL_W + 0.02, ROW1_Y + 0.30, 0.21, 0.24,
                  "right")

    # ---------------------------------------------------------- row 2 ------
    t = tb(s, 0.69, 2.74, 5.00, 0.20)
    write(t, "RETRAINING-UPDATE PATH", size=11, bold=True, color=TEAL)

    row2 = [
        ("", "Incoming Update",
         "from a device, hub or vendor cloud  ·  any may be hostile"),
        ("M4", "Graft onto Trusted Core",
         "1,100 reference rows  ·  update weighted to a realistic share"),
        ("M5", "Train Shadow Model",
         "a what-if model: what this update would actually produce"),
        ("M6", "CCS Gate",
         "six components scored on the bank  ·  calibrated threshold"),
    ]
    for i, (tag, head, sub) in enumerate(row2):
        accent = AMBER if i == 3 else TEAL
        node(s, COL_X[i], ROW2_Y, COL_W, BOX_H, tag, head, sub, accent=accent)
        if i < 3:
            arrow(s, COL_X[i] + COL_W + 0.02, ROW2_Y + 0.30, 0.21, 0.24,
                  "right")

    # bank feeds the gate
    gate_cx = COL_X[3] + COL_W / 2
    arrow(s, gate_cx - 0.12, ROW1_Y + BOX_H + 0.02, 0.24, 0.42, "down")
    t = tb(s, gate_cx + 0.20, ROW1_Y + BOX_H + 0.08, 1.60, 0.22)
    write(t, "scored against", size=10, italic=True, color=SLATE)

    # ------------------------------------------------- fork and bus --------
    run(s, gate_cx - 0.03, ROW2_Y + BOX_H + 0.02, 0.06, BUS_Y - ROW2_Y
        - BOX_H - 0.02, color=RULE)
    laneA_cx = 0.69 + 5.61 / 2
    laneB_cx = 7.03 + 5.61 / 2
    run(s, laneA_cx, BUS_Y, gate_cx - laneA_cx, 0.05, color=RULE)

    for cx, label, colour in ((laneA_cx, "ACCEPT", TEAL),
                              (laneB_cx, "QUARANTINE", RED)):
        arrow(s, cx - 0.12, BUS_Y + 0.05, 0.24, 0.24, "down", color=colour)
        t = tb(s, cx + 0.18, BUS_Y + 0.06, 1.70, 0.22)
        write(t, label, size=10.5, bold=True, color=colour)

    # ---------------------------------------------------------- row 3 ------
    lanes = [
        (0.69, TEAL, "SAFE — VALIDATED CONTRIBUTION",
         [("M7", "Safe Pool",
           "rows tagged with their contributor"),
          ("M8", "Immunize + Retrain",
           "vaccines from the twins' own futures"),
          ("M9", "Promotion Gates",
           "accuracy · resistance · FPR · size")]),
        (7.03, RED, "SUSPICIOUS — HELD OUT OF TRAINING",
         [("M10", "Quarantine",
           "held intact with its verdict report"),
          ("M11", "Forensics",
           "attribution and per-row evidence"),
          ("M12", "Purge + Rollback",
           "excise contributor, restore model")]),
    ]
    for lane_x, colour, header, items in lanes:
        t = tb(s, lane_x, ROW3_Y - 0.22, 5.61, 0.20)
        write(t, header, size=10.5, bold=True, color=colour)
        for j, (tag, head, sub) in enumerate(items):
            x = lane_x + j * 1.93
            node(s, x, ROW3_Y, 1.75, ROW3_H, tag, head, sub, accent=colour,
                 head_size=11.5, sub_size=9.5)
            if j < 2:
                arrow(s, x + 1.77, ROW3_Y + 0.24, 0.14, 0.22, "right",
                      color=colour)

    # ---------------------------------------------------------- row 4 ------
    box(s, COL_X[1], ROW4_Y, 8.02, ROW4_H, fill=NAVY, border=None)
    t = tb(s, COL_X[1] + 0.20, ROW4_Y + 0.10, 7.62, 0.24)
    write(t, "TRUSTED THREAT DETECTOR", size=13, bold=True, color=WHITE)
    t = tb(s, COL_X[1] + 0.20, ROW4_Y + 0.34, 7.62, 0.24)
    write(t, "promoted only through the gates, or reinstated by rollback  ·  "
             "this is the model that serves live verdicts",
          size=10.5, color=RULE)

    for cx, colour in ((0.69 + 2 * 1.93 + 1.75 / 2, TEAL),
                       (7.03 + 2 * 1.93 + 1.75 / 2, RED)):
        arrow(s, cx - 0.12, ROW3_Y + ROW3_H + 0.04, 0.24,
              ROW4_Y - ROW3_Y - ROW3_H - 0.04, "down", color=colour)

    # ------------------------------------------------- feedback loop -------
    y_mid = ROW4_Y + ROW4_H / 2
    run(s, COL_X[1] + 8.02, y_mid - 0.03, LOOP_X - (COL_X[1] + 8.02), 0.06)
    run(s, LOOP_X, ROW1_Y + 0.40, 0.06, y_mid - ROW1_Y - 0.40 + 0.03)
    arrow(s, COL_X[3] + COL_W + 0.02, ROW1_Y + 0.30, LOOP_X - COL_X[3]
          - COL_W - 0.02 + 0.06, 0.24, "left")
    t = tb(s, LOOP_X - 2.45, y_mid - 0.30, 2.30, 0.24, align=PP_ALIGN.RIGHT)
    write(t, "the promoted model re-filters the bank", size=10,
          italic=True, color=SLATE)

    takeaway(s, "Why this is a loop, not a pipeline:",
             "the promoted detector re-filters the audit bank, so every "
             "future update is judged against scenarios the current model "
             "already handles — the gate sharpens as the model improves.")
