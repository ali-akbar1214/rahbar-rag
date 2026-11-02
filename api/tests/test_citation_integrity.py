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
