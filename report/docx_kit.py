"""Word-formatting helpers for the Project-I report.

The faculty template prescribes exact typography, so everything here is direct
formatting rather than named styles — a style the reviewer's Word resolves
differently would silently break the specification.

Prescribed by the template:
    Title (cover)   Times New Roman 16, bold, UPPER CASE, line spacing 1.5
    Names           Times New Roman 13, bold, UPPER CASE, line spacing 1.5
    Heading 1       Times New Roman 14, bold, UPPER CASE, line spacing 1.5
    Heading 2       Times New Roman 13, bold, Title Case, line spacing 1.5
    Heading 3       Times New Roman 12, bold + italic, Title Case, spacing 1.5
    Body            Times New Roman 12, line spacing 1.15
"""
from __future__ import annotations

import re

from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_UNDERLINE, WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

FONT = "Times New Roman"
BLACK = RGBColor(0, 0, 0)

_bookmark_id = [1000]


# ---------------------------------------------------------------- runs -----
def _style_run(run, *, size, bold=False, italic=False, caps=False,
               color=BLACK, font=FONT, underline=None):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.all_caps = caps
    if underline is not None:
        run.font.underline = underline
    # East-Asian font must be set explicitly or Word substitutes its own.
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font)
    return run


def para(doc_or_cell, text="", *, size=12, bold=False, italic=False,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=1.15, before=0, after=6,
         indent=0.0, left=None, caps=False, color=BLACK,
         keep_with_next=False, underline=None):
    p = doc_or_cell.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = align
    pf.line_spacing = line
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if indent:
        pf.first_line_indent = Inches(indent)
    if left is not None:
        pf.left_indent = Inches(left)
    pf.keep_with_next = keep_with_next
    if text:
        _style_run(p.add_run(text), size=size, bold=bold, italic=italic,
                   caps=caps, color=color, underline=underline)
    return p


def body(doc, text, *, indent=0.5, after=8):
    """A justified body paragraph with the template's first-line indent."""
    return para(doc, text, size=12, line=1.15, indent=indent, after=after)


def bullet(doc, text, *, size=12, bold_lead=None, level=0):
    p = doc.add_paragraph(style="List Bullet")
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.line_spacing = 1.15
    pf.space_after = Pt(4)
    pf.left_indent = Inches(0.4 + 0.3 * level)
    if bold_lead:
        _style_run(p.add_run(bold_lead), size=size, bold=True)
    _style_run(p.add_run(text), size=size)
    return p


def numbered(doc, text, *, size=12, bold_lead=None):
    p = doc.add_paragraph(style="List Number")
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.line_spacing = 1.15
    pf.space_after = Pt(4)
    pf.left_indent = Inches(0.4)
    if bold_lead:
        _style_run(p.add_run(bold_lead), size=size, bold=True)
    _style_run(p.add_run(text), size=size)
    return p


# ------------------------------------------------------------ bookmarks ----
def bookmark(paragraph, name):
    """Wrap a paragraph in a bookmark so a PAGEREF field can target it."""
    _bookmark_id[0] += 1
    bid = str(_bookmark_id[0])
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bid)
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bid)
    paragraph._p.insert(0, start)
    paragraph._p.append(end)
    return name


def pageref(paragraph, bookmark_name, *, size=12, bold=False):
    """A PAGEREF field: Word fills in the real page number on update."""
    run = paragraph.add_run()
    _style_run(run, size=size, bold=bold)
    fld = OxmlElement("w:fldChar")
    fld.set(qn("w:fldCharType"), "begin")
    run._r.append(fld)

    run = paragraph.add_run()
    _style_run(run, size=size, bold=bold)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" PAGEREF {bookmark_name} \\h "
    run._r.append(instr)

    run = paragraph.add_run()
    _style_run(run, size=size, bold=bold)
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    run._r.append(sep)

    run = paragraph.add_run("1")          # placeholder until fields refresh
    _style_run(run, size=size, bold=bold)

    run = paragraph.add_run()
    _style_run(run, size=size, bold=bold)
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)


# -------------------------------------------------------------- headings ---
_CHAPTER_NUM = re.compile(r"^\s*(\d+)\.\s*(.+)$")


def front_heading(doc, text, *, page_break=True, bookmark_name=None):
    """DECLARATION / CERTIFICATE / ACKNOWLEDGEMENTS.

    The template sets these at 14 pt bold, centred, with a thick underline.
    """
    if page_break:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    p = para(doc, text.upper(), size=14, bold=True,
             align=WD_ALIGN_PARAGRAPH.CENTER, line=1.0, before=0, after=14,
             left=0.26, underline=WD_UNDERLINE.THICK, keep_with_next=True)
    if bookmark_name:
        bookmark(p, bookmark_name)
    return p


def h1(doc, text, *, bookmark_name=None, page_break=True):
    """A chapter opening.

    The template puts "CHAPTER n" centred at 16 pt bold on its own line, and
    the chapter title left-aligned at 14 pt bold beneath it. A heading with no
    leading number -- the appendix -- is centred on one line instead.
    """
    if page_break:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    match = _CHAPTER_NUM.match(text)
    if match is None:
        p = para(doc, text.upper(), size=14, bold=True,
                 align=WD_ALIGN_PARAGRAPH.CENTER, line=1.08, before=0,
                 after=12, keep_with_next=True)
        if bookmark_name:
            bookmark(p, bookmark_name)
        return p

    number, title = match.group(1), match.group(2)
    para(doc, f"CHAPTER {number}", size=16, bold=True,
         align=WD_ALIGN_PARAGRAPH.CENTER, line=1.08, before=0, after=8,
         keep_with_next=True)
    p = para(doc, f"{number}. {title.upper()}", size=14, bold=True,
             align=WD_ALIGN_PARAGRAPH.LEFT, line=1.08, before=0, after=10,
             keep_with_next=True)
    if bookmark_name:
        bookmark(p, bookmark_name)
    return p


def h2(doc, text, *, bookmark_name=None):
    p = para(doc, text, size=13, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT,
             line=1.15, before=12, after=6, keep_with_next=True)
    if bookmark_name:
        bookmark(p, bookmark_name)
    return p


def h3(doc, text, *, bookmark_name=None):
    p = para(doc, text, size=12, bold=True,
             align=WD_ALIGN_PARAGRAPH.LEFT, line=1.15, before=10, after=4,
             keep_with_next=True)
    if bookmark_name:
        bookmark(p, bookmark_name)
    return p


# ---------------------------------------------------------------- figures --
def figure(doc, path, caption, *, width=6.1):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(4)
    p.add_run().add_picture(str(path), width=Inches(width))
    cap = para(doc, caption, size=11, italic=False,
               align=WD_ALIGN_PARAGRAPH.CENTER, line=1.0, after=12)
    return cap


# ----------------------------------------------------------------- tables --
def set_cell_borders(cell, *, colour="D7DEE9", size=6, edges=None):
    edges = edges or ("top", "left", "bottom", "right")
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    for edge in edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:color"), colour)
        borders.append(el)


def clear_cell_borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tcPr.append(borders)


def shade_cell(cell, hex_fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def cell_text(cell, text, *, size=11, bold=False, italic=False,
              align=WD_ALIGN_PARAGRAPH.LEFT, line=1.0):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.line_spacing = line
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    _style_run(p.add_run(text), size=size, bold=bold, italic=italic)
    return p


def grid(doc, rows, widths, *, head_size=11, body_size=10.5, header=True,
         header_fill="1F2A44", header_colour=RGBColor(0xFF, 0xFF, 0xFF)):
    """A bordered table with a shaded header row."""
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.width = Inches(widths[c])
            set_cell_borders(cell)
            if r == 0 and header:
                shade_cell(cell, header_fill)
                cell.text = ""
                p = cell.paragraphs[0]
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                _style_run(p.add_run(str(value)), size=head_size, bold=True,
                           color=header_colour)
            else:
                cell_text(cell, str(value), size=body_size)
    for row in table.rows:
        for c, cell in enumerate(row.cells):
            cell.width = Inches(widths[c])
    return table


# ---------------------------------------------------------------- sections -
def page_numbering(section, fmt="decimal", start=1, *, show=True):
    """Set the numbering format and restart value for a section."""
    sectPr = section._sectPr
    old = sectPr.find(qn("w:pgNumType"))
    if old is not None:
        sectPr.remove(old)
    el = OxmlElement("w:pgNumType")
    el.set(qn("w:fmt"), fmt)
    el.set(qn("w:start"), str(start))
    sectPr.append(el)

    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if not show:
        return
    run = p.add_run()
    _style_run(run, size=11)
    for kind, text in (("begin", None), (None, " PAGE "), ("separate", None),
                       (None, None), ("end", None)):
        if kind:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), kind)
            run._r.append(fld)
        elif text:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = text
            run._r.append(instr)


def new_section(doc):
    return doc.add_section(WD_SECTION.NEW_PAGE)
