"""Tests for cleaning rules and structural preservation."""

from __future__ import annotations

from pipeline.clean import clean
from pipeline.models import Document, Page


def test_clean_preserves_single_occurring_headings() -> None:
    doc = Document(
        source="handbook.pdf",
        doc_version="2026",
        superseded=False,
        pages=[
            Page(source="handbook.pdf", page=1, text="### Section 1.1 Scope\nContent for section 1.1\nPage 1 of 50"),
            Page(source="handbook.pdf", page=2, text="### Section 1.2 Eligibility\nContent for section 1.2\nPage 2 of 50"),
        ],
    )
    cleaned = clean(doc)
    # Headings must be preserved
    assert "Section 1.1 Scope" in cleaned.pages[0].text
    assert "Section 1.2 Eligibility" in cleaned.pages[1].text
    # Page numbers should be stripped
    assert "Page 1 of 50" not in cleaned.pages[0].text


def test_clean_empty_document_handling() -> None:
    doc = Document(source="empty.pdf", doc_version="2026", superseded=False, pages=[])
    assert clean(doc).pages == []
