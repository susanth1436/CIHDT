"""Re-typeset a PPTX into Times New Roman at a larger size.

    python report/retypeset.py <input.pptx> [output.pptx]

Operates on the packaged XML directly rather than rebuilding the deck, so any
edits made in PowerPoint survive the change.

Sizes are scaled in tiers rather than by one factor.  Small text is what
actually hurts readability from the back of a room, so it gets the largest
increase; display type is already legible and only needs a nudge, and scaling
it as hard would break the title layouts.
"""
from __future__ import annotations

import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

FONT = "Times New Roman"

# (upper bound in points, multiplier)
TIERS = [(11.0, 1.15), (16.0, 1.10), (float("inf"), 1.05)]

FONT_ATTR = re.compile(r'(<a:(?:latin|ea|cs|sym)\b[^>]*?typeface=")([^"]*)(")')
SIZE_ATTR = re.compile(r'\bsz="(\d+)"')

# Parts whose typography we rewrite.  Notes and comments are left alone.
TARGETS = ("ppt/slides/slide", "ppt/slideLayouts/slideLayout",
           "ppt/slideMasters/slideMaster", "ppt/theme/theme")


def scale_size(hundredths: int) -> int:
    pt = hundredths / 100.0
    for limit, factor in TIERS:
        if pt <= limit:
            scaled = pt * factor
            break
    # Round to the nearest half point: PowerPoint shows halves cleanly.
    return int(round(scaled * 2) / 2 * 100)


def retypeset(src: Path, dst: Path) -> dict:
    stats = Counter()
    size_map: dict[float, float] = {}

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
            dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if any(item.filename.startswith(t) for t in TARGETS) and \
                    item.filename.endswith(".xml"):
                xml = data.decode("utf-8")

                def swap_font(m):
                    if m.group(2) != FONT:
                        stats["fonts"] += 1
                    return m.group(1) + FONT + m.group(3)

                xml = FONT_ATTR.sub(swap_font, xml)

                def swap_size(m):
                    old = int(m.group(1))
                    new = scale_size(old)
                    if new != old:
                        stats["sizes"] += 1
                        size_map[old / 100] = new / 100
                    return f'sz="{new}"'

                xml = SIZE_ATTR.sub(swap_size, xml)
                data = xml.encode("utf-8")
                stats["parts"] += 1
            zout.writestr(item, data)

    return {"stats": stats, "size_map": dict(sorted(size_map.items()))}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    dst = (Path(sys.argv[2]) if len(sys.argv) > 2
           else src.with_name(src.stem + "_TNR.pptx"))
    if not src.exists():
        print(f"not found: {src}")
        return 1

    result = retypeset(src, dst)
    s = result["stats"]
    print(f"source : {src.name}")
    print(f"output : {dst}")
    print(f"\nrewrote {s['parts']} XML parts, "
          f"{s['fonts']} font references, {s['sizes']} size attributes\n")
    print("point-size mapping:")
    for old, new in result["size_map"].items():
        print(f"   {old:>5.1f}  ->  {new:>5.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
