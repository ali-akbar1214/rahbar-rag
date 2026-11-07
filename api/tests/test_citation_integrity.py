"""Tests for citation matching and page number reconciliation."""

from __future__ import annotations

from app.schemas import Answer, Citation, Passage
from app.services.grounding import validate_citations


def test_validate_citations_resolves_page_from_passages() -> None:
    passages = [
        Passage(chunk_id="c1", text="Text", source="doc.pdf", section="1.1", page=7, score=0.91)
    ]
    # Citation with page=None should have page resolved from matching passage
    ans = Answer(
        reasoning="Reasoning",
        answer="Grounded text",
        citations=[Citation(source="doc.pdf", section="1.1", page=None)],
        answered_from_context=True,
        confidence="high",
    )
    validated = validate_citations(ans, passages)
    assert len(validated.citations) == 1
    assert validated.citations[0].page == 7


def test_validate_citations_strips_fabricated_section_on_valid_source() -> None:
    passages = [
        Passage(chunk_id="c1", text="80% attendance", source="doc.pdf", section="1.21 Attendance", page=4, score=0.93)
    ]
    ans = Answer(
        reasoning="Reasoning",
        answer="Grounded text",
        citations=[
            Citation(source="doc.pdf", section="1.21 Attendance", page=4),
            Citation(source="doc.pdf", section="9.99 Fabricated Clause", page=99),
        ],
        answered_from_context=True,
        confidence="high",
    )
    validated = validate_citations(ans, passages)
    assert len(validated.citations) == 1
    assert validated.citations[0].section == "1.21 Attendance"
