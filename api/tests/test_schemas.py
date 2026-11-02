"""Tests for API contract schemas and validation boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import Answer, AskRequest, Citation, Passage, RetrievedRef


def test_ask_request_length_boundaries() -> None:
    # 3 characters: valid
    req = AskRequest(question="Why")
    assert req.question == "Why"

    # 2 characters: invalid
    with pytest.raises(ValidationError):
        AskRequest(question="No")

    # 500 characters: valid
    req500 = AskRequest(question="a" * 500)
    assert len(req500.question) == 500

    # 501 characters: invalid
    with pytest.raises(ValidationError):
        AskRequest(question="a" * 501)


def test_answer_schema_contract() -> None:
    ans = Answer(
        reasoning="Test reasoning",
        answer="Test answer",
        citations=[Citation(source="test.pdf", section="1.1", page=1)],
        answered_from_context=True,
        confidence="high",
    )
    assert ans.confidence == "high"
    assert len(ans.citations) == 1


def test_passage_score_description() -> None:
    p = Passage(
        chunk_id="chk-01",
        text="Sample text",
        source="sample.pdf",
        section="Intro",
        page=1,
        score=0.88,
    )
    assert p.score == 0.88
    ref = RetrievedRef(
        chunk_id=p.chunk_id,
        source=p.source,
        section=p.section,
        page=p.page,
        score=p.score,
    )
    assert ref.chunk_id == "chk-01"
