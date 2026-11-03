"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

import re
from collections import Counter

from .models import Document, Page


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them.
    """
    if not doc.pages:
        return doc

    # Detect repeating header and footer lines across pages
    first_lines: Counter[str] = Counter()
    last_lines: Counter[str] = Counter()

    for p in doc.pages:
        lines = [ln.strip() for ln in p.text.splitlines() if ln.strip()]
        if len(lines) >= 1:
            first_lines[lines[0]] += 1
        if len(lines) >= 2:
            last_lines[lines[-1]] += 1

    total_pages = len(doc.pages)
    threshold = max(2, int(total_pages * 0.4))

    repeating_headers = {ln for ln, count in first_lines.items() if count >= threshold and len(ln) < 100}
    repeating_footers = {ln for ln, count in last_lines.items() if count >= threshold and len(ln) < 100}

    cleaned_pages: list[Page] = []
    for p in doc.pages:
        lines = p.text.splitlines()
        processed_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            # Drop repeating page numbers / headers / footers
            if stripped in repeating_headers or stripped in repeating_footers:
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
