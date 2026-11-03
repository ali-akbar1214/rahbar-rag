"""Tests for honest abstention generation and confidence ratings."""

from __future__ import annotations

from app.services.grounding import make_abstention_answer


def test_make_abstention_structure() -> None:
    ans = make_abstention_answer("Missing hostel document")
    assert ans.answered_from_context is False
    assert ans.confidence == "low"
    assert ans.citations == []
    assert "cannot answer" in ans.answer.lower()
    assert "Abstention triggered" in ans.reasoning
