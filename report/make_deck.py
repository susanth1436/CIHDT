"""Assemble the CIHDT Review-2 deck.

    python report/make_deck.py

Writes report/CIHDT_Review2.pptx (13.333 x 7.5 in, 16:9).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pptx import Presentation                                    # noqa: E402
from pptx.util import Inches                                     # noqa: E402

import build_review2 as base                                     # noqa: E402
import slides_a, slides_b, slides_c, slides_d                    # noqa: E402
import slides_gap                                                # noqa: E402

BUILDERS = [
    slides_a.slide_title,
    slides_a.slide_compliance,
    slides_a.slide_aim,
    slides_a.slide_abstract,
    slides_a.slide_lit1,
    slides_a.slide_lit2,
    slides_gap.slide_gap,
    slides_b.slide_objectives,
    slides_b.slide_architecture,
    slides_d.slide_blockdiagram,
    slides_b.slide_frs,
    slides_b.slide_modules,
    slides_c.slide_experiments,
    slides_c.slide_results,
    slides_c.slide_synthesis,
    slides_c.slide_references,
]


def main() -> int:
    prs = Presentation()
    prs.slide_width = Inches(base.W)
    prs.slide_height = Inches(base.H)

    for i, build in enumerate(BUILDERS, start=1):
        build(prs)
        print(f"  slide {i:>2}  {build.__name__}")

    out = HERE / "CIHDT_Review2.pptx"
    prs.save(out)
    print(f"\nwrote {out}  ({out.stat().st_size / 1024:.0f} KB, "
          f"{len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
