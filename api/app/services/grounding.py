"""Grounding verification, untrusted passage sanitization, citation matching, and honest abstention."""

from __future__ import annotations

import re
from ..schemas import Answer, Citation, Passage

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|your|above)\s+instructions?[^.\n]*[.\n]?", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|your|system)\s+instructions?[^.\n]*[.\n]?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:in\s+developer\s+mode|unrestricted)[^.\n]*[.\n]?", re.IGNORECASE),
    re.compile(r"system\s*:\s*override[^.\n]*[.\n]?", re.IGNORECASE),
    re.compile(r"bypass\s+(?:guardrails?|grounding)[^.\n]*[.\n]?", re.IGNORECASE),
    re.compile(r"say\s+(?:that\s+)?the\s+policy\s+permits\s+it[^.\n]*[.\n]?", re.IGNORECASE),
]


def detect_injection(text: str) -> bool:
    """Detect prompt-injection directives in user queries or untrusted document chunks."""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def sanitize_passages(passages: list[Passage]) -> list[Passage]:
    """Treat retrieved text strictly as untrusted data (section 3.4).

    Strips embedded prompt-injection directives from poisoned chunks. If a chunk consists
    solely of an injection payload with no substantive policy text left, drops it so no
    downstream provider can obey or echo the injected instruction.
    """
    cleaned_list: list[Passage] = []
    for p in passages:
        sanitized = p.text
        had_injection = False
        for pattern in INJECTION_PATTERNS:
            if pattern.search(sanitized):
                had_injection = True
                sanitized = pattern.sub(" ", sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        if had_injection and len(sanitized) < 20:
            continue
        cleaned_list.append(
            Passage(
                chunk_id=p.chunk_id,
                text=sanitized,
                source=p.source,
                section=p.section,
                page=p.page,
                score=p.score,
            )
        )
    return cleaned_list


def _sections_match(cited_sec: str, passage_sec: str) -> bool:
    """Verify cited section matches a retrieved chunk's section via prefix, substring, or clause token."""
    c_norm = cited_sec.lower().strip()
    p_norm = passage_sec.lower().strip()
    if not c_norm or not p_norm:
        return False
    if c_norm in p_norm or p_norm in c_norm:
        return True
    c_tokens = {tok for tok in re.findall(r"[a-z0-9.]+", c_norm) if len(tok) > 1 or tok.isdigit()}
    p_tokens = {tok for tok in re.findall(r"[a-z0-9.]+", p_norm) if len(tok) > 1 or tok.isdigit()}
    return len(c_tokens.intersection(p_tokens)) > 0


def _sources_match(cited_src: str, passage_src: str) -> bool:
    c_src = cited_src.lower().strip()
    p_src = passage_src.lower().strip()
    return bool(c_src and p_src and (c_src == p_src or c_src in p_src or p_src in c_src))


def validate_citations(answer: Answer, passages: list[Passage]) -> Answer:
    """Ensure every citation strictly matches both source and section of a retrieved chunk (sections 3.4 & 5.3)."""
    if not answer.answered_from_context or not passages:
        return Answer(
            reasoning=answer.reasoning,
            answer=answer.answer,
            citations=[],
            answered_from_context=answer.answered_from_context,
            confidence=answer.confidence,
        )

    filtered_citations: list[Citation] = []
    for c in answer.citations:
        matched_passage: Passage | None = None
        for p in passages:
            if _sources_match(c.source, p.source) and _sections_match(c.section, p.section):
                matched_passage = p
                break
        if matched_passage is not None:
            matched_page = c.page if c.page is not None else matched_passage.page
            filtered_citations.append(
                Citation(
                    source=matched_passage.source,
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
