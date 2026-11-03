"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import Document, Page

pypdf: Any = None
pdfplumber: Any = None
pytesseract: Any = None
convert_from_path: Any = None

try:
    import pypdf as _pypdf
    pypdf = _pypdf
except ImportError:
    pass

try:
    import pdfplumber as _pdfplumber
    pdfplumber = _pdfplumber
except ImportError:
    pass

try:
    import pytesseract as _pytesseract
    from pdf2image import convert_from_path as _convert_from_path
    pytesseract = _pytesseract
    convert_from_path = _convert_from_path
except ImportError:
    pass


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them; mark those pages ocr=True.
    Supports PDF, Markdown, and HTML documents.
    """
    file_path = Path(path)
    source_name = file_path.name
    doc = Document(source=source_name, doc_version=doc_version, superseded=superseded)

    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        pages = _extract_pdf(file_path, source_name)
    elif suffix in {".md", ".txt"}:
        pages = _extract_text_file(file_path, source_name)
    elif suffix in {".html", ".htm"}:
        pages = _extract_html_file(file_path, source_name)
    else:
        # Fallback raw reading
        text = file_path.read_text(encoding="utf-8", errors="replace")
        pages = [Page(source=source_name, page=1, text=text, ocr=False)]

    doc.pages = pages
    return doc


def _extract_pdf(file_path: Path, source_name: str) -> list[Page]:
    pages: list[Page] = []

    # Primary: pdfplumber for high-fidelity text and table extraction
    if pdfplumber is not None:
        try:
            with pdfplumber.open(file_path) as pdf:
                for idx, p in enumerate(pdf.pages, start=1):
                    text = p.extract_text() or ""
                    # Also extract tables if present and format as markdown
                    tables = p.extract_tables() or []
                    if tables:
                        table_strs = []
                        for tbl in tables:
                            formatted = _format_table(tbl)
                            if formatted:
                                table_strs.append(formatted)
                        if table_strs:
                            text += "\n\n" + "\n\n".join(table_strs)

                    is_ocr = False
                    if len(text.strip()) < 30 and pytesseract is not None and convert_from_path is not None:
                        # Attempt OCR on scanned page
                        try:
                            images = convert_from_path(file_path, first_page=idx, last_page=idx)
                            if images:
                                ocr_text = pytesseract.image_to_string(images[0])
                                if len(ocr_text.strip()) > 10:
                                    text = ocr_text
                                    is_ocr = True
                        except Exception:
                            # OCR system tool unavailable; document loss gracefully
                            text = f"[OCR Required: Scanned image page {idx} - no native text layer]"
                            is_ocr = True

                    pages.append(Page(source=source_name, page=idx, text=text, ocr=is_ocr))
                if pages:
                    return pages
        except Exception:
            pass

    # Secondary fallback: pypdf
    if pypdf is not None:
        try:
            reader = pypdf.PdfReader(str(file_path))
            for idx, p in enumerate(reader.pages, start=1):
                text = p.extract_text() or ""
                pages.append(Page(source=source_name, page=idx, text=text, ocr=False))
            if pages:
                return pages
        except Exception:
            pass

    return [Page(source=source_name, page=1, text="", ocr=False)]


def _extract_text_file(file_path: Path, source_name: str) -> list[Page]:
    content = file_path.read_text(encoding="utf-8", errors="replace")
    # Strip optional YAML front matter (--- ... ---) used by fixture files
    content = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)
    # Split by form-feed or treat as multi-page
    raw_pages = content.split("\x0c") if "\x0c" in content else [content]
    pages: list[Page] = []
    for idx, pt in enumerate(raw_pages, start=1):
        pages.append(Page(source=source_name, page=idx, text=pt, ocr=False))
    return pages


def _extract_html_file(file_path: Path, source_name: str) -> list[Page]:
    raw = file_path.read_text(encoding="utf-8", errors="replace")
    clean_text = re.sub(r"<script.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r"<style.*?</style>", "", clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(
        r"<h[1-6][^>]*>(.*?)</h[1-6]>",
        lambda m: "\n\n## " + re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip() + "\n\n",
        clean_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    clean_text = re.sub(r"</tr\s*>", "\n", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"</t[dh]\s*>", " | ", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"<(?:br|p|/p|/div|/li)\b[^>]*>", "\n", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"<[^>]+>", " ", clean_text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in clean_text.splitlines()]
    normalized = re.sub(r"\n{3,}", "\n\n", "\n".join(ln for ln in lines if ln)).strip()
    return [Page(source=source_name, page=1, text=normalized, ocr=False)]


def _format_table(table_rows: list[list[str | None]]) -> str:
    """Format extracted pdfplumber table into markdown."""
    valid_rows = [[(cell or "").replace("\n", " ").strip() for cell in row] for row in table_rows if any(row)]
    if not valid_rows:
        return ""
    col_count = max(len(row) for row in valid_rows)
    # Pad rows
    padded = [row + [""] * (col_count - len(row)) for row in valid_rows]
    lines = []
    header = padded[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    for r in padded[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)
