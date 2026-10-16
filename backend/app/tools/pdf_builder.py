"""PDF builder (section 6, page 25): generates a clean, printable PDF file from document sections or Markdown.

Uses a deterministic pure-Python PDF generator so every document can be exported
and downloaded as a real `%PDF-1.4` file in any environment.
"""
import re
from pathlib import Path


def _pdf_escape(text: str) -> str:
    clean = text.encode("latin-1", "replace").decode("latin-1")
    return clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_line(text: str, width: int = 82) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def build_from_doc(doc: dict, out: Path) -> Path:
    title = str(doc.get("title") or "Document")[:120]
    template = str(doc.get("template") or "technical_report").replace("_", " ").title()
    items: list[tuple[str, str]] = [("title", title), ("meta", f"Template: {template}")]
    if doc.get("abstract"):
        items.append(("h2", "Abstract"))
        for ln in _wrap_line(str(doc["abstract"]), 80):
            items.append(("body", ln))
    for idx, sec in enumerate(doc.get("sections", []), 1):
        heading = str(sec.get("heading") or f"Section {idx}")
        items.append(("h1", f"{idx}. {heading}"))
        for p in sec.get("paragraphs", []):
            for ln in _wrap_line(str(p), 82):
                items.append(("body", ln))
            items.append(("spacer", ""))
        for b in sec.get("bullets", []):
            for j, ln in enumerate(_wrap_line(str(b), 76)):
                items.append(("bullet" if j == 0 else "bullet_cont", ln))
        if sec.get("chart") and isinstance(sec["chart"], dict):
            items.append(("caption", f"Figure {idx}: {sec['chart'].get('title', 'Chart')}"))
    if doc.get("references"):
        items.append(("h1", "References"))
        for ref in doc.get("references", []):
            for ln in _wrap_line(str(ref), 80):
                items.append(("body", ln))
    return _write_pdf(title, items, out)


def build_from_markdown(title: str, markdown_text: str, out: Path) -> Path:
    items: list[tuple[str, str]] = [("title", title[:120])]
    for raw in markdown_text.splitlines():
        line = raw.strip()
        if not line:
            items.append(("spacer", ""))
        elif line.startswith("# "):
            items.append(("h1", line[2:].strip()))
        elif line.startswith("## "):
            items.append(("h2", line[3:].strip()))
        elif line.startswith("### "):
            items.append(("h2", line[4:].strip()))
        elif re.match(r"^[-*]\s+", line):
            body = re.sub(r"^[-*]\s+", "", line)
            for j, ln in enumerate(_wrap_line(body, 76)):
                items.append(("bullet" if j == 0 else "bullet_cont", ln))
        else:
            for ln in _wrap_line(line, 82):
                items.append(("body", ln))
    return _write_pdf(title, items, out)


def _write_pdf(title: str, items: list[tuple[str, str]], out: Path) -> Path:
    pages: list[list[tuple[str, str]]] = [[]]
    y = 740
    for kind, text in items:
        step = {"title": 28, "meta": 20, "h1": 24, "h2": 20, "body": 15, "bullet": 15, "bullet_cont": 15, "caption": 18, "spacer": 8}.get(kind, 15)
        if y - step < 65:
            pages.append([])
            y = 740
        pages[-1].append((kind, text))
        y -= step

    total_pages = len(pages)
    objects: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_regular = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    pages_obj_idx = add_obj(b"")
    page_ids = []

    for pno, pitems in enumerate(pages, 1):
        cmds = [
            "0.45 0.50 0.56 rg",
            f"BT /F1 9 Tf 54 795 Td ({_pdf_escape(title[:70])}) Tj ET",
            f"BT /F1 9 Tf 480 36 Td (Page {pno} of {total_pages}) Tj ET",
            "0.82 0.85 0.89 RG 0.5 w 54 788 m 558 788 l S",
        ]
        cy = 756
        for kind, text in pitems:
            if kind == "spacer":
                cy -= 8
                continue
            if kind == "title":
                cmds.append("0.12 0.23 0.37 rg")
                cmds.append(f"BT /F2 20 Tf 54 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 28
            elif kind == "meta":
                cmds.append("0.35 0.42 0.49 rg")
                cmds.append(f"BT /F1 10 Tf 54 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 20
            elif kind == "h1":
                cy -= 6
                cmds.append("0.16 0.50 0.44 rg")
                cmds.append(f"BT /F2 14 Tf 54 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 20
            elif kind == "h2":
                cy -= 4
                cmds.append("0.12 0.23 0.37 rg")
                cmds.append(f"BT /F2 12 Tf 54 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 17
            elif kind == "bullet":
                cmds.append("0.13 0.15 0.18 rg")
                cmds.append(f"BT /F1 11 Tf 66 {cy} Td (- {_pdf_escape(text)}) Tj ET")
                cy -= 15
            elif kind == "bullet_cont":
                cmds.append("0.13 0.15 0.18 rg")
                cmds.append(f"BT /F1 11 Tf 76 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 15
            elif kind == "caption":
                cmds.append("0.16 0.50 0.44 rg")
                cmds.append(f"BT /F2 10 Tf 54 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 18
            else:
                cmds.append("0.13 0.15 0.18 rg")
                cmds.append(f"BT /F1 11 Tf 54 {cy} Td ({_pdf_escape(text)}) Tj ET")
                cy -= 15
        stream_bytes = "\n".join(cmds).encode("latin-1")
        content_id = add_obj(b"<< /Length " + str(len(stream_bytes)).encode() + b" >>\nstream\n" + stream_bytes + b"\nendstream")
        page_id = add_obj(
            f"<< /Type /Page /Parent {pages_obj_idx} 0 R /MediaBox [0 0 612 842] "
            f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode("latin-1")
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_obj_idx - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_obj_idx} 0 R >>".encode("latin-1"))

    out.parent.mkdir(parents=True, exist_ok=True)
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(buf))
        buf.extend(f"{i} 0 obj\n".encode("latin-1"))
        buf.extend(obj)
        buf.extend(b"\nendobj\n")
    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    buf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    out.write_bytes(bytes(buf))
    return out
