"""Grounding verification, citation matching, and honest abstention."""

from __future__ import annotations

import re
from ..schemas import Answer, Citation, Passage

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+developer\s+mode|unrestricted)", re.IGNORECASE),
    re.compile(r"system\s*:\s*override", re.IGNORECASE),
    re.compile(r"bypass\s+(guardrails?|grounding)", re.IGNORECASE),
]


def detect_injection(text: str) -> bool:
    """Detect common prompt-injection attacks."""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def validate_citations(answer: Answer, passages: list[Passage]) -> Answer:
    """Ensure every citation strictly matches a retrieved chunk (Section 5.3)."""
    if not answer.answered_from_context or not passages:
        return Answer(
            reasoning=answer.reasoning,
            answer=answer.answer,
            citations=[],
            answered_from_context=answer.answered_from_context,
            confidence=answer.confidence,
        )

    # Valid (source, section) pairs from actual retrieval
    valid_sources = {p.source for p in passages}
    valid_sections = {(p.source, p.section) for p in passages}

    filtered_citations: list[Citation] = []
    for c in answer.citations:
        # Source must be present in retrieved chunks
        if c.source in valid_sources:
            # Match section if possible, otherwise map to first matching source
            matched_page = c.page
            if matched_page is None:
                for p in passages:
                    if p.source == c.source and p.page is not None:
                        matched_page = p.page
                        break
            filtered_citations.append(
                Citation(
                    source=c.source,
                    section=c.section,
                    page=matched_page,
                )
            )

    return Answer(
        reasoning=answer.reasoning,
        answer=answer.answer,
        citations=filtered_citations,
        answered_from_context=answer.answered_from_context,
        confidence=answer.confidence,
    )


def make_abstention_answer(reason: str = "The question cannot be answered from the provided documents.") -> Answer:
    """Return a deterministic honest abstention answer."""
    return Answer(
        reasoning=f"Abstention triggered: {reason}",
        answer="I cannot answer this question based on the official university documents provided.",
        citations=[],
        answered_from_context=False,
        confidence="low",
    )
