"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
from collections import Counter

from .models import Document, Page


def _norm_banner(line: str) -> str:
    """Normalize digits and spacing so running headers/footers with page numbers match across pages."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line.strip())).strip().lower()


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them.
    """
    if not doc.pages:
        return doc

    # Detect repeating header (first 3 lines) and footer (last 2 lines) banners across pages
    header_counts: Counter[str] = Counter()
    footer_counts: Counter[str] = Counter()

    for p in doc.pages:
        lines = [ln.strip() for ln in p.text.splitlines() if ln.strip()]
        for ln in lines[:3]:
            if len(ln) < 100:
                header_counts[_norm_banner(ln)] += 1
        for ln in lines[-2:]:
            if len(ln) < 100 and len(lines) >= 3:
                footer_counts[_norm_banner(ln)] += 1

    total_pages = len(doc.pages)
    threshold = max(2, int(total_pages * 0.35))

    repeating_headers = {k for k, count in header_counts.items() if count >= threshold}
    repeating_footers = {k for k, count in footer_counts.items() if count >= threshold}

    cleaned_pages: list[Page] = []
    for p in doc.pages:
        lines = p.text.splitlines()
        processed_lines: list[str] = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            norm = _norm_banner(stripped) if stripped else ""
            # Drop repeating page numbers / headers / footers
            if idx < 5 and norm in repeating_headers:
                continue
            if idx >= max(0, len(lines) - 4) and norm in repeating_footers:
                continue
            if re.fullmatch(r"Page\s+\d+(\s+of\s+\d+)?|\d+", stripped, re.IGNORECASE):
                continue
            processed_lines.append(line)

        cleaned_text = "\n".join(processed_lines)
        # Normalize multiple blank lines to double newlines (preserving paragraph structure)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
        cleaned_pages.append(Page(source=p.source, page=p.page, text=cleaned_text, ocr=p.ocr))

    return Document(
        source=doc.source,
        doc_version=doc.doc_version,
        superseded=doc.superseded,
        pages=cleaned_pages,
    )
