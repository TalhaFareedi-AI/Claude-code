"""Document builder (section 6, page 26): JSON sections in, a professionally styled Word file out (python-docx).

Templates:
  - research_paper: Abstract, Table of Contents summary, numbered sections, figures, and references.
  - technical_report: Executive summary, numbered sections, shaded data tables, and figure captions.
  - proposal: Problem statement, proposed solution, milestones, budget/metrics table, and next steps.

Typography & styling rules (page 26):
  - Real Word styles: Title, Heading 1 to 3, Body (11 pt, line spacing 1.15), Caption, Quote.
  - One accent color for headings and shaded table headers; dark text on white.
  - Header with document title, footer with page numbers, even 1-inch margins.
"""
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from .. import charts

TEMPLATES = {
    "research_paper": {"accent": "1E4E79", "label": "Research Paper"},
    "technical_report": {"accent": "1F6B5C", "label": "Technical Report"},
    "proposal": {"accent": "3B4990", "label": "Project Proposal"},
}


def check_doc(doc: dict) -> list[str]:
    problems = []
    for i, s in enumerate(doc.get("sections", []), 1):
        if not s.get("heading"):
            problems.append(f"section {i} has no heading")
        if not (s.get("paragraphs") or s.get("bullets")):
            problems.append(f"section {i} is empty")
    return problems


def _shade_cell(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _add_page_number_field(run) -> None:
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")
    r = run._r
    r.append(fldChar1)
    r.append(instrText)
    r.append(fldChar2)
    r.append(fldChar3)


def build(doc: dict, out: Path, template: str | None = None) -> Path:
    tpl_key = (template or doc.get("template") or "technical_report").lower().strip()
    if tpl_key not in TEMPLATES:
        tpl_key = "technical_report"
    tpl = TEMPLATES[tpl_key]
    accent_rgb = RGBColor.from_string(tpl["accent"])
    dark_rgb = RGBColor(0x1E, 0x29, 0x3B)
    muted_rgb = RGBColor(0x64, 0x74, 0x8B)

    d = Document()

    # Page margins (1 inch even margins) and header/footer
    for section in d.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        hdr = section.header.paragraphs[0]
        hdr.text = str(doc.get("title", "Document"))[:90]
        hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if hdr.runs:
            hdr.runs[0].font.size = Pt(9)
            hdr.runs[0].font.color.rgb = muted_rgb
        ftr = section.footer.paragraphs[0]
        ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = ftr.add_run("Page ")
        r1.font.size = Pt(9)
        r1.font.color.rgb = muted_rgb
        r_pg = ftr.add_run()
        r_pg.font.size = Pt(9)
        r_pg.font.color.rgb = muted_rgb
        _add_page_number_field(r_pg)

    # Normal style: 11pt body floor, 1.15 line spacing
    normal = d.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = dark_rgb
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(6)

    title_text = str(doc.get("title", "Document"))[:120]
    title_p = d.add_heading(title_text, 0)
    for r in title_p.runs:
        r.font.color.rgb = accent_rgb
        r.font.size = Pt(22)

    sections = doc.get("sections", [])

    # Research paper extras: Abstract & Table of Contents summary
    if tpl_key == "research_paper" or doc.get("abstract"):
        abs_text = str(doc.get("abstract") or (sections[0]["paragraphs"][0] if sections and sections[0].get("paragraphs") else ""))[:800]
        if abs_text:
            h_abs = d.add_heading("Abstract", level=2)
            for r in h_abs.runs:
                r.font.color.rgb = accent_rgb
            p_abs = d.add_paragraph(abs_text)
            p_abs.paragraph_format.left_indent = Inches(0.25)
            p_abs.paragraph_format.right_indent = Inches(0.25)
        if len(sections) > 1:
            h_toc = d.add_heading("Contents", level=2)
            for r in h_toc.runs:
                r.font.color.rgb = accent_rgb
            for idx, s in enumerate(sections, 1):
                d.add_paragraph(f"{idx}. {s.get('heading', f'Section {idx}')}")

    fig_no = 0
    for idx, s in enumerate(sections, 1):
        raw_heading = str(s.get("heading", ""))[:120]
        numbered_heading = raw_heading if raw_heading[:1].isdigit() else f"{idx}. {raw_heading}"
        h1 = d.add_heading(numbered_heading, 1)
        for r in h1.runs:
            r.font.color.rgb = accent_rgb
            r.font.size = Pt(15)

        for para in s.get("paragraphs", []):
            p = d.add_paragraph(str(para))
            p.paragraph_format.line_spacing = 1.15

        for b in s.get("bullets", []):
            d.add_paragraph(str(b), style="List Bullet")

        if s.get("chart"):
            try:
                rec = charts.validate(s["chart"])
                data = charts.compute(rec)
                fig_no += 1
                cap = d.add_paragraph(f"Figure {fig_no}: {rec['title']}")
                cap.runs[0].bold = True
                cap.runs[0].font.size = Pt(10)
                cap.runs[0].font.color.rgb = accent_rgb
                names = [x["name"] for x in data["series"]]
                t = d.add_table(rows=1, cols=1 + len(names))
                t.alignment = WD_TABLE_ALIGNMENT.CENTER
                t.style = "Table Grid"
                hdr_cells = t.rows[0].cells
                hdr_cells[0].text = rec.get("x", {}).get("label", "Item")
                _shade_cell(hdr_cells[0], tpl["accent"])
                for r in hdr_cells[0].paragraphs[0].runs:
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                    r.font.size = Pt(10)
                for j, n in enumerate(names):
                    hdr_cells[j + 1].text = n
                    _shade_cell(hdr_cells[j + 1], tpl["accent"])
                    hdr_cells[j + 1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    for r in hdr_cells[j + 1].paragraphs[0].runs:
                        r.font.bold = True
                        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                        r.font.size = Pt(10)
                labels = data.get("labels") or [f"{x:.3g}" for x in data["xs"]]
                step = max(1, len(labels) // 10)
                for i in range(0, len(labels), step):
                    row = t.add_row().cells
                    row[0].text = str(labels[i])
                    for j, sr in enumerate(data["series"]):
                        row[j + 1].text = f"{sr['values'][i]:.4g}"
                        row[j + 1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            except Exception:
                pass

    if doc.get("references"):
        h_ref = d.add_heading("References", 1)
        for r in h_ref.runs:
            r.font.color.rgb = accent_rgb
        for ref in doc.get("references", []):
            d.add_paragraph(str(ref), style="List Number")

    out.parent.mkdir(parents=True, exist_ok=True)
    d.save(out)
    return out
