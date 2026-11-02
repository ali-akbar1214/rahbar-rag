"""Tests for chunk overlap boundary conditions."""

from __future__ import annotations

from pipeline.chunk import chunk
from pipeline.models import Document, Page


def test_chunk_overlap_boundary_preservation() -> None:
    text = (
        "FAST National University requires 80% attendance. "
        "Students who fail to meet attendance are barred from examinations. "
        "A student placed on warning must achieve a CGPA of 2.00 or higher."
    )
    doc = Document(
        source="test-rules.md",
        doc_version="2026",
        superseded=False,
        pages=[Page(source="test-rules.md", page=1, text=text)],
    )

    chunks = chunk(doc, size=80, overlap=25)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.source == "test-rules.md"
        assert c.page == 1
        assert c.doc_version == "2026"
        assert c.superseded is False


def test_chunk_empty_page() -> None:
    doc = Document(
        source="blank.md",
        doc_version="2026",
        superseded=False,
        pages=[Page(source="blank.md", page=1, text="   \n\n  ")],
    )
    chunks = chunk(doc, size=100, overlap=20)
    assert len(chunks) == 0
