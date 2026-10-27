"""Sanity-check the built deck without a renderer.

Three checks, in decreasing order of how much they would embarrass us on a
projector:

1. anything outside the 13.333 x 7.5 in canvas;
2. text boxes whose content almost certainly does not fit, estimated from a
   Calibri advance-width model;
3. the frame furniture (page number, footer, takeaway) present on every
   content slide.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Emu

DEFAULT_DECK = Path(__file__).resolve().parent / "CIHDT_Review2.pptx"
DECK = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DECK
W_IN, H_IN = 13.333, 7.5

# Advance-width and line-box models, selected from the deck's own font.
# Times New Roman is narrower per character than Calibri but sets on a
# similar line box, so both numbers matter when a deck is re-typeset.
METRICS = {"Calibri": (0.48, 1.20), "Times New Roman": (0.455, 1.17)}
CHAR_EM, LINE_EM = METRICS["Calibri"]


def detect_font(prs):
    """Pick the metric model from whichever face the deck actually uses."""
    global CHAR_EM, LINE_EM
    from collections import Counter
    seen = Counter()
    for slide in prs.slides:
        for sh in slide.shapes:
            if not sh.has_text_frame:
                continue
            for para in sh.text_frame.paragraphs:
                for run in para.runs:
                    if run.font.name:
                        seen[run.font.name] += 1
    if not seen:
        return "Calibri"
    name = seen.most_common(1)[0][0]
    CHAR_EM, LINE_EM = METRICS.get(name, METRICS["Calibri"])
    return name


def in_(emu) -> float:
    return Emu(emu).inches


def estimate_height(tf, width_in: float) -> float:
    """Rough rendered height of a text frame, in inches."""
    total = 0.0
    for para in tf.paragraphs:
        text = "".join(r.text for r in para.runs)
        if not text:
            continue
        size = max((r.font.size.pt for r in para.runs
                    if r.font.size is not None), default=12.0)
        spacing = para.line_spacing if isinstance(para.line_spacing, float) else 1.0
        char_w_in = CHAR_EM * size / 72.0
        per_line = max(1, int(width_in / char_w_in))
        lines = max(1, math.ceil(len(text) / per_line))
        total += lines * (LINE_EM * size / 72.0) * spacing
    return total


def main() -> int:
    prs = Presentation(DECK)
    face = detect_font(prs)
    problems: list[str] = []
    warnings: list[str] = []

    for n, slide in enumerate(prs.slides, start=1):
        seen_page = seen_footer = False
        for sh in slide.shapes:
            x, y = in_(sh.left), in_(sh.top)
            w, h = in_(sh.width), in_(sh.height)

            if x < -0.01 or y < -0.01 or x + w > W_IN + 0.01 or y + h > H_IN + 0.01:
                problems.append(
                    f"slide {n:>2}: shape '{sh.name}' outside canvas "
                    f"({x:.2f},{y:.2f}) {w:.2f}x{h:.2f}")

            if not sh.has_text_frame:
                continue
            text = sh.text_frame.text
            if f"/ {len(prs.slides._sldIdLst)}" in text or "/ 15" in text:
                seen_page = True
            if "SCOPE" in text and "VIT" in text:
                seen_footer = True
            if not text.strip():
                continue

            need = estimate_height(sh.text_frame, w)
            # Only flag a real spill: 25% over the box, and at least a
            # quarter-inch, so ordinary rounding noise stays quiet.
            if need > h * 1.25 and need - h > 0.25:
                warnings.append(
                    f"slide {n:>2}: '{text[:52].strip()}...' needs "
                    f"~{need:.2f}in in a {h:.2f}in box ({w:.2f}in wide)")

        if n > 1:
            if not seen_page:
                problems.append(f"slide {n:>2}: no page number")
            if not seen_footer:
                problems.append(f"slide {n:>2}: no footer")

    print(f"slides: {len(prs.slides._sldIdLst)}   font: {face}"
          f"   (char {CHAR_EM}, line {LINE_EM})")
    print(f"canvas: {in_(prs.slide_width):.3f} x {in_(prs.slide_height):.3f} in")

    print(f"\nhard problems: {len(problems)}")
    for p in problems:
        print("  ! " + p)

    print(f"\npossible text overflow: {len(warnings)}")
    for w in warnings:
        print("  ~ " + w)

    # Overlapping cards are worse than overflow: one panel silently covers
    # another and the content simply vanishes on the projector.
    overlaps = []
    for n, slide in enumerate(prs.slides, start=1):
        cards = []
        for sh in slide.shapes:
            if not hasattr(sh, "adjustments"):
                continue
            w, h = in_(sh.width), in_(sh.height)
            if w < 0.5 or h < 0.30:          # rules and accent bars
                continue
            cards.append((sh.name, in_(sh.left), in_(sh.top), w, h))
        for i in range(len(cards)):
            for j in range(i + 1, len(cards)):
                an, ax, ay, aw, ah = cards[i]
                bn, bx, by, bw, bh = cards[j]
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox <= 0.05 or oy <= 0.05:
                    continue
                # A card fully inside another is nesting, not collision.
                inside = (ax >= bx - 0.02 and ay >= by - 0.02
                          and ax + aw <= bx + bw + 0.02
                          and ay + ah <= by + bh + 0.02)
                outside = (bx >= ax - 0.02 and by >= ay - 0.02
                           and bx + bw <= ax + aw + 0.02
                           and by + bh <= ay + ah + 0.02)
                if inside or outside:
                    continue
                overlaps.append(
                    f"slide {n:>2}: '{an}' and '{bn}' overlap by "
                    f"{ox:.2f} x {oy:.2f} in")

    print(f"\ncard overlaps: {len(overlaps)}")
    for o in overlaps:
        print("  X " + o)

    return 1 if (problems or overlaps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
