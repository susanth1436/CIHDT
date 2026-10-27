"""The Gamma theme, rebuilt natively in PowerPoint.

The theme tokens were read straight off the reference deck
(gamma.app/docs/malware-cryw8uy2atanx1r) rather than guessed:

    --heading-font   Petrona      --heading-color  #000000
    --body-font      Inter        --body-color     #272525
    --accent-color   #007EBD      --card-color     #FFFFFF at 75% alpha
    card radius 10.8px, hairline ring #E6E6E6, soft misty-blue page behind

Petrona and Inter are web fonts and are not installed on this machine, so
the two closest universally available substitutes are used: Georgia for the
serif headings and Segoe UI for the body. Both are metrically similar enough
that the deck keeps its look on any Windows machine in the review room,
which a Google-font dependency would not.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

# -- tokens -----------------------------------------------------------------
HEAD_FONT = "Georgia"            # stands in for Petrona
BODY_FONT = "Segoe UI"           # stands in for Inter

HEADING = RGBColor(0x00, 0x00, 0x00)
BODY = RGBColor(0x27, 0x25, 0x25)
ACCENT = RGBColor(0x00, 0x7E, 0xBD)
MUTED = RGBColor(0x66, 0x66, 0x6B)
CARD = RGBColor(0xFF, 0xFF, 0xFF)
RING = RGBColor(0xE6, 0xE6, 0xE6)
OK = RGBColor(0x2C, 0x8C, 0x2C)
WARN = RGBColor(0xB4, 0x73, 0x00)

SLIDE_W, SLIDE_H = Inches(13.333), Inches(7.5)

# card geometry, matching the reference deck's generous margins
CARD_L, CARD_T = Inches(0.52), Inches(0.42)
CARD_W, CARD_H = Inches(12.29), Inches(6.30)
PAD = Inches(0.62)                       # inner padding of the card
BODY_L = CARD_L + PAD
BODY_W = CARD_W - 2 * PAD

FOOTER = "28/10/26          SCOPE"


# ===========================================================================
# Background
# ===========================================================================
def make_background(path: Path, w: int = 2560, h: int = 1440) -> Path:
    """The soft misty page the reference theme floats its cards on.

    Painted rather than downloaded, so the deck carries no external asset
    and no licence question: a pale lavender bloom in the top-left corner
    falling away to a blue-grey haze along the bottom edge.
    """
    if path.exists():
        return path

    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = x / (w - 1), y / (h - 1)

    # base: white at the top, settling into a cool blue-grey at the foot
    base = np.stack([
        np.full_like(v, 1.00) - 0.14 * v ** 1.6,
        np.full_like(v, 1.00) - 0.08 * v ** 1.6,
        np.full_like(v, 1.00) - 0.02 * v ** 1.6,
    ], axis=-1)

    def bloom(cx, cy, r, tint, strength):
        d = np.sqrt(((u - cx) / r) ** 2 + ((v - cy) / (r * w / h)) ** 2)
        m = np.clip(1.0 - d, 0.0, 1.0) ** 2.0 * strength
        return m[..., None] * (np.array(tint, np.float32) - base)

    base = base + bloom(0.06, -0.05, 0.85, (0.976, 0.925, 0.980), 0.55)
    base = base + bloom(0.00, 1.05, 0.70, (0.760, 0.855, 0.910), 0.80)
    base = base + bloom(1.04, 0.95, 0.75, (0.870, 0.925, 0.955), 0.45)

    # the faint horizontal banding that reads as distant mist
    band = 0.012 * np.sin(v * 26.0) * np.clip(v - 0.45, 0, 1) ** 1.2
    base = base + band[..., None]

    img = Image.fromarray(
        (np.clip(base, 0, 1) * 255).astype(np.uint8), mode="RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path


# ===========================================================================
# Primitives
# ===========================================================================
def _alpha(shape, pct: float):
    """Give a solid fill an alpha channel, which python-pptx cannot."""
    solid = shape.fill._xPr.find(qn("a:solidFill"))
    clr = solid.find(qn("a:srgbClr"))
    clr.append(clr.makeelement(qn("a:alpha"),
                               {"val": str(int(pct * 1000))}))


def _no_shadow(shape):
    spPr = shape._element.spPr
    spPr.append(spPr.makeelement(qn("a:effectLst"), {}))


def blank(prs, bg: Path, card=True, card_alpha=86.0):
    """A slide carrying the page background and, usually, the white card."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.shapes.add_picture(str(bg), 0, 0, SLIDE_W, SLIDE_H)
    if card:
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                     CARD_L, CARD_T, CARD_W, CARD_H)
        box.adjustments[0] = 0.022            # ~10.8 px at this size
        box.fill.solid()
        box.fill.fore_color.rgb = CARD
        _alpha(box, card_alpha)
        box.line.color.rgb = RING
        box.line.width = Pt(1)
        _no_shadow(box)
        box.text_frame.text = ""
    return slide


def textbox(slide, left, top, width, height):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.clear()
    return tf


def run(para, text, *, font=BODY_FONT, size=14, bold=False, italic=False,
        color=BODY, caps=False):
    r = para.add_run()
    r.text = text
    f = r.font
    f.name = font
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color
    if caps:
        r.text = text.upper()
    return r


def line(tf, text="", *, first=False, size=14, bold=False, italic=False,
         color=BODY, font=BODY_FONT, align=PP_ALIGN.LEFT, space_before=0,
         space_after=6, line_spacing=1.18, indent=0.0):
    p = tf.paragraphs[0] if (first and not tf.paragraphs[0].runs) \
        else tf.add_paragraph()
    p.alignment = align
    p.space_before = Pt(space_before)
    p.space_after = Pt(space_after)
    p.line_spacing = line_spacing
    if indent:
        p.paragraph_format.left_indent = Inches(indent) \
            if hasattr(p, "paragraph_format") else None
        _indent(p, indent)
    if text:
        run(p, text, font=font, size=size, bold=bold, italic=italic,
            color=color)
    return p


def _indent(p, inches):
    pPr = p._pPr if p._pPr is not None else p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(inches))))
    pPr.set("indent", "0")


def bullet(tf, text, *, lead="", size=13.5, color=BODY, indent=0.30,
           space_after=7, lead_color=None, dot=True):
    """A bullet drawn with a bare accent dot, as the reference deck does."""
    p = tf.add_paragraph() if (tf.paragraphs[0].runs or
                               len(tf.paragraphs) > 1) else tf.paragraphs[0]
    p.space_before = Pt(0)
    p.space_after = Pt(space_after)
    p.line_spacing = 1.16
    _hanging(p, indent)
    if dot:
        run(p, "●  ", size=size * 0.62, color=ACCENT, bold=True)
    if lead:
        run(p, lead, size=size, bold=True, color=lead_color or HEADING)
    run(p, text, size=size, color=color)
    return p


def _hanging(p, inches):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(inches))))
    pPr.set("indent", str(int(-Inches(inches))))


# ===========================================================================
# Slide furniture
# ===========================================================================
def heading(slide, text, *, eyebrow="", size=31, top=None):
    """Serif heading with the thin accent rule the reference theme uses."""
    t = top if top is not None else CARD_T + Inches(0.46)
    if eyebrow:
        tf = textbox(slide, BODY_L, t - Inches(0.30), BODY_W, Inches(0.26))
        line(tf, eyebrow.upper(), first=True, size=10.5, bold=True,
             color=ACCENT, space_after=0)
    tf = textbox(slide, BODY_L, t, BODY_W, Inches(0.62))
    line(tf, text, first=True, font=HEAD_FONT, size=size, bold=True,
         color=HEADING, space_after=0, line_spacing=1.0)

    rule = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, BODY_L, t + Inches(0.60), Inches(1.15),
        Pt(2.6))
    rule.fill.solid()
    rule.fill.fore_color.rgb = ACCENT
    rule.line.fill.background()
    _no_shadow(rule)
    return t + Inches(0.92)


def footer(slide, number):
    tf = textbox(slide, BODY_L, SLIDE_H - Inches(0.52), BODY_W, Inches(0.26))
    p = line(tf, "", first=True, size=9.5, space_after=0)
    run(p, FOOTER, size=9.5, color=MUTED)
    tf2 = textbox(slide, CARD_L, SLIDE_H - Inches(0.52),
                  CARD_W - PAD, Inches(0.26))
    p2 = line(tf2, "", first=True, size=9.5, space_after=0,
              align=PP_ALIGN.RIGHT)
    run(p2, str(number), size=9.5, bold=True, color=MUTED)


# ===========================================================================
# Tables
# ===========================================================================
def table(slide, rows, widths, left, top, *, head_size=11.5, body_size=10.5,
          row_h=0.34, head_h=0.38, aligns=None, zebra=True):
    total_w = Inches(sum(widths))
    height = Inches(head_h + row_h * (len(rows) - 1))
    gf = slide.shapes.add_table(len(rows), len(widths), left, top,
                                total_w, height)
    tbl = gf.table
    # drop the banded style PowerPoint applies by default
    tbl._tbl.find(qn("a:tblPr")).set("bandRow", "0")
    tbl._tbl.find(qn("a:tblPr")).set("firstRow", "0")

    for i, wd in enumerate(widths):
        tbl.columns[i].width = Inches(wd)
    tbl.rows[0].height = Inches(head_h)
    for r in range(1, len(rows)):
        tbl.rows[r].height = Inches(row_h)

    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.02)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = RGBColor(0xE8, 0xF3, 0xF9)
            elif zebra and r % 2 == 0:
                cell.fill.fore_color.rgb = RGBColor(0xF7, 0xFA, 0xFC)
            else:
                cell.fill.fore_color.rgb = CARD
            _cell_borders(cell, top_=(r == 0), head=(r == 0))

            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.line_spacing = 1.06
            p.space_before = Pt(0)
            p.space_after = Pt(0)
            if aligns:
                p.alignment = aligns[c]
            elif c == 0:
                p.alignment = PP_ALIGN.LEFT
            run(p, str(value), size=head_size if r == 0 else body_size,
                bold=(r == 0), color=HEADING if r == 0 else BODY)
    return gf


def _cell_borders(cell, *, top_=False, head=False):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag, on in (("a:lnT", top_), ("a:lnB", True)):
        ln = tcPr.makeelement(qn(tag), {"w": "9525", "cap": "flat",
                                        "cmpd": "sng", "algn": "ctr"})
        fill = ln.makeelement(qn("a:solidFill"), {})
        clr = ln.makeelement(qn("a:srgbClr"),
                             {"val": "007EBD" if head else "E6E6E6"})
        fill.append(clr)
        ln.append(fill)
        tcPr.append(ln)


# ===========================================================================
# Callouts
# ===========================================================================
def callout(slide, left, top, width, height, title, text, *,
            tint=RGBColor(0xE8, 0xF3, 0xF9), accent=ACCENT, title_size=12.5,
            text_size=11.5, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                 left, top, width, height)
    box.adjustments[0] = 0.08
    box.fill.solid()
    box.fill.fore_color.rgb = tint
    box.line.color.rgb = accent
    box.line.width = Pt(0.75)
    _no_shadow(box)

    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.16)
    tf.margin_top = tf.margin_bottom = Inches(0.11)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_after = Pt(2)
    p.line_spacing = 1.05
    run(p, title, font=HEAD_FONT, size=title_size, bold=True, color=accent)
    if text:
        p2 = tf.add_paragraph()
        p2.alignment = align
        p2.space_after = Pt(0)
        p2.line_spacing = 1.12
        run(p2, text, size=text_size, color=BODY)
    return box


def stat(slide, left, top, width, value, label, *, color=ACCENT,
         value_size=25, label_size=10):
    tf = textbox(slide, left, top, width, Inches(0.78))
    p = line(tf, "", first=True, align=PP_ALIGN.CENTER, space_after=1,
             line_spacing=1.0)
    run(p, value, font=HEAD_FONT, size=value_size, bold=True, color=color)
    p2 = line(tf, "", align=PP_ALIGN.CENTER, space_after=0, line_spacing=1.05)
    run(p2, label, size=label_size, color=MUTED)
