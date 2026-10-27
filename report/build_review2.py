"""Build the Review-2 deck for the CIHDT project.

The visual language is taken from the reference deck supplied by the team:
13.333 x 7.5 in white canvas, Calibri, a navy/teal palette, flat cards with
hairline borders, and a fixed slide frame (eyebrow, title, subtitle, a
takeaway band, and a footer rule).

The *content* is this project's own, and it is written against what the code
actually does rather than what earlier drafts claimed it would do.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = Path(__file__).resolve().parent / "CIHDT_Review2.pptx"

# ---------------------------------------------------------------- palette --
INK      = RGBColor(0x0E, 0x17, 0x29)   # darkest navy, titles
NAVY     = RGBColor(0x1F, 0x2A, 0x44)   # headings
SLATE    = RGBColor(0x55, 0x61, 0x7A)   # secondary text
TEAL     = RGBColor(0x0E, 0x8C, 0x79)   # accent
AMBER    = RGBColor(0xB8, 0x72, 0x0A)   # caution / in-progress
RED      = RGBColor(0xC0, 0x39, 0x2B)   # negative
CARD     = RGBColor(0xEE, 0xF2, 0xF8)   # card fill
CARD2    = RGBColor(0xE4, 0xE9, 0xF2)   # alternate fill
RULE     = RGBColor(0xD7, 0xDE, 0xE9)   # hairlines and borders
WHITE    = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Times New Roman"


def pt_scale(size: float) -> float:
    """Times sets smaller on the page than Calibri at the same nominal size.

    Every size is therefore scaled up, and small text gains most: it is what
    fails first when a slide is read from the back of a room.  Display type is
    already legible and only gets a nudge, because scaling it as hard would
    burst the title blocks.
    """
    for limit, factor in ((11.0, 1.15), (16.0, 1.10), (float("inf"), 1.05)):
        if size <= limit:
            return round(size * factor * 2) / 2
    return size
DATE = "04-09-2026"
TOTAL_SLIDES = 16

W, H = 13.333, 7.5


# ------------------------------------------------------------- primitives --
def tb(slide, x, y, w, h, *, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """A margin-free, word-wrapping text box."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    return tf


def write(tf, text, *, size=13, bold=False, color=NAVY, para=0,
          space_after=0, line=None, italic=False):
    """Write one paragraph, adding paragraphs as needed."""
    while len(tf.paragraphs) <= para:
        tf.add_paragraph()
    p = tf.paragraphs[para]
    p.space_after = Pt(space_after)
    if line:
        p.line_spacing = line
    run = p.add_run()
    run.text = text
    run.font.size = Pt(pt_scale(size))
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = FONT
    return p


def rich(tf, parts, *, para=0, space_after=0, line=None):
    """One paragraph made of several differently-styled runs.

    `parts` is a list of (text, kwargs) where kwargs may set size, bold,
    color, italic.
    """
    while len(tf.paragraphs) <= para:
        tf.add_paragraph()
    p = tf.paragraphs[para]
    p.space_after = Pt(space_after)
    if line:
        p.line_spacing = line
    for text, style in parts:
        run = p.add_run()
        run.text = text
        run.font.size = Pt(pt_scale(style.get("size", 13)))
        run.font.bold = style.get("bold", False)
        run.font.italic = style.get("italic", False)
        run.font.color.rgb = style.get("color", NAVY)
        run.font.name = FONT
    return p


def box(slide, x, y, w, h, *, fill=CARD, border=RULE, radius=True, line_w=0.75):
    """A flat card. No shadow, hairline border."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        shape.adjustments[0] = 0.06
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if border is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = border
        shape.line.width = Pt(line_w)
    shape.shadow.inherit = False
    shape.text_frame.word_wrap = True
    return shape


def bar(slide, x, y, w, h, color):
    """A solid rule or accent bar."""
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                   Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def chip(slide, x, y, w, text, *, color=TEAL, fill=None, size=10.5, h=0.24):
    """A small status pill."""
    if fill is not None:
        box(slide, x, y, w, h, fill=fill, border=None)
    t = tb(slide, x, y + 0.02, w, h, align=PP_ALIGN.CENTER)
    write(t, text.upper(), size=size, bold=True, color=color)


def eyebrow_title(slide, n, section, title, subtitle):
    """The standard header block on every content slide."""
    t = tb(slide, 0.55, 0.32, 12.23, 0.24)
    rich(t, [(f"{n:02d}", {"size": 14, "bold": True, "color": TEAL}),
             ("   ·   ", {"size": 14, "color": RULE}),
             (section.upper(), {"size": 14, "bold": True, "color": SLATE})])
    t = tb(slide, 0.55, 0.58, 10.5, 0.52)
    write(t, title, size=30, bold=True, color=INK)
    t = tb(slide, 0.55, 1.14, 11.5, 0.26)
    write(t, subtitle, size=15, color=SLATE)
    bar(slide, 0.55, 1.46, 12.23, 0.012, RULE)


def takeaway(slide, label, text, *, y=6.40, h=0.50, size=14.5):
    """The bordered band above the footer carrying the slide's one point.

    `y` and `h` flex for the few slides whose closing statement genuinely
    needs two lines rather than one.
    """
    box(slide, 0.69, y, 11.95, h, fill=CARD, border=RULE)
    bar(slide, 0.69, y, 0.05, h, TEAL)
    t = tb(slide, 0.90, y + 0.10, 11.60, h - 0.16, anchor=MSO_ANCHOR.TOP)
    rich(t, [(label + "  ", {"size": size, "bold": True, "color": TEAL}),
             (text, {"size": size, "color": NAVY})], line=1.02)


def footer(slide, page):
    bar(slide, 0.55, 6.99, 12.23, 0.012, RULE)
    t = tb(slide, 0.55, 7.06, 2.0, 0.22)
    write(t, DATE, size=12.5, color=SLATE)
    t = tb(slide, 5.20, 7.06, 2.90, 0.22, align=PP_ALIGN.CENTER)
    write(t, "SCOPE  ·  VIT", size=12.5, color=SLATE)
    t = tb(slide, 10.78, 7.06, 2.0, 0.22, align=PP_ALIGN.RIGHT)
    write(t, f"{page} / {TOTAL_SLIDES}", size=12.5, color=SLATE)


def new_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = WHITE
    return slide


def frame(prs, n, section, title, subtitle, page):
    slide = new_slide(prs)
    eyebrow_title(slide, n, section, title, subtitle)
    footer(slide, page)
    return slide


def grid_table(slide, x, y, w, rows, widths, *, header_h=0.34, row_h=0.42,
               head_size=11.5, body_size=10.5, first_bold=True):
    """A flat table drawn as cards, so it obeys the deck's visual language."""
    total = sum(widths)
    widths = [wi * w / total for wi in widths]
    # header
    box(slide, x, y, w, header_h, fill=NAVY, border=None)
    cx = x
    for wi, cell in zip(widths, rows[0]):
        t = tb(slide, cx + 0.09, y + 0.07, wi - 0.18, header_h - 0.1)
        write(t, cell, size=head_size, bold=True, color=WHITE)
        cx += wi
    # body
    cy = y + header_h
    for r, row in enumerate(rows[1:]):
        fill = WHITE if r % 2 == 0 else CARD
        box(slide, x, cy, w, row_h, fill=fill, border=RULE, radius=False,
            line_w=0.5)
        cx = x
        for c, (wi, cell) in enumerate(zip(widths, row)):
            t = tb(slide, cx + 0.09, cy + 0.05, wi - 0.18, row_h - 0.08,
                   anchor=MSO_ANCHOR.TOP)
            colour = NAVY if c == 0 and first_bold else SLATE
            emphasis = c == 0 and first_bold
            if isinstance(cell, tuple):          # (text, colour) status chip
                cell, colour = cell
                emphasis = True
            write(t, cell, size=body_size, bold=emphasis, color=colour,
                  line=0.92)
            cx += wi
        cy += row_h
    return cy
