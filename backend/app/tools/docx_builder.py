"""Document builder: JSON sections in, a real Word file out (python-docx)."""
from pathlib import Path

from docx import Document

from .. import charts


def check_doc(doc: dict) -> list[str]:
    problems = []
    for i, s in enumerate(doc.get("sections", []), 1):
        if not s.get("heading"):
            problems.append(f"section {i} has no heading")
        if not (s.get("paragraphs") or s.get("bullets")):
            problems.append(f"section {i} is empty")
    return problems


def build(doc: dict, out: Path) -> Path:
    d = Document()
    d.add_heading(str(doc.get("title", "Document"))[:120], 0)
    for s in doc.get("sections", []):
        d.add_heading(str(s.get("heading", ""))[:120], 1)
        for para in s.get("paragraphs", []):
            d.add_paragraph(str(para))
        for b in s.get("bullets", []):
            d.add_paragraph(str(b), style="List Bullet")
        if s.get("chart"):
            try:
                rec = charts.validate(s["chart"])
                data = charts.compute(rec)
                d.add_paragraph(f"Chart: {rec['title']}").runs[0].bold = True
                names = [x["name"] for x in data["series"]]
                t = d.add_table(rows=1, cols=1 + len(names))
                t.style = "Light Grid Accent 1"
                t.rows[0].cells[0].text = rec.get("x", {}).get("label", "Item")
                for j, n in enumerate(names):
                    t.rows[0].cells[j + 1].text = n
                labels = data.get("labels") or [f"{x:.3g}" for x in data["xs"]]
                step = max(1, len(labels) // 10)
                for i in range(0, len(labels), step):
                    row = t.add_row().cells
                    row[0].text = str(labels[i])
                    for j, sr in enumerate(data["series"]):
                        row[j + 1].text = f"{sr['values'][i]:.4g}"
            except Exception:
                pass
    out.parent.mkdir(parents=True, exist_ok=True)
    d.save(out)
    return out
