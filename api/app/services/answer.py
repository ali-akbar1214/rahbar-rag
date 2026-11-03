"""Turns a question into an AskResponse through retrieval, caching, generation, and grounding."""

from __future__ import annotations

import logging

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..schemas import AskResponse, RetrievedRef
from .cache import SemanticCache
from .grounding import detect_injection, make_abstention_answer, validate_citations

log = logging.getLogger("rahbar.answer")
_global_cache: SemanticCache | None = None


def get_cache(settings: Settings) -> SemanticCache:
    global _global_cache
    if _global_cache is None or _global_cache.settings != settings:
        _global_cache = SemanticCache(settings)
    return _global_cache


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings
) -> AskResponse:
    """Production query pipeline:
    1. Check Semantic Cache.
    2. Guard against prompt injection.
    3. Retrieve passages and filter by relevance floor.
    4. Honest abstention if no passages qualify.
    5. Generate structured answer with retry & fallback.
    6. Validate citations against retrieved passages.
    7. Update cache (never-cache abstentions).
    """
    request_id = request_id_var.get()
    cache = get_cache(settings)

    # 1. Check Semantic Cache
    cached_resp = cache.get(question)
    if cached_resp is not None:
        log.info(
            "cache hit for question",
            extra={
                "request_id": request_id,
                "provider": provider.name,
                "cached": True,
            },
        )
        return AskResponse(
            request_id=request_id,
            answer=cached_resp.answer,
            citations=cached_resp.citations,
            answered_from_context=cached_resp.answered_from_context,
            confidence=cached_resp.confidence,
            retrieved=cached_resp.retrieved,
            provider=f"{provider.name} (cached)",
        )

    # 2. Guard against prompt injection
    if detect_injection(question):
        log.warning("prompt injection attempt detected", extra={"request_id": request_id, "question": question})
        abstain = make_abstention_answer("Prompt injection detected.")
        return AskResponse(
            request_id=request_id,
            answer=abstain.answer,
            citations=[],
            answered_from_context=False,
            confidence="low",
            retrieved=[],
            provider=provider.name,
        )

    # 3. Retrieve passages
    passages = retriever.retrieve(question, k=settings.top_k)
    scores = [round(p.score, 4) for p in passages]

    # 4. Relevance floor and honest abstention
    if not passages or (passages and max(scores) < settings.relevance_floor):
        log.info(
            "abstaining: retrieved passages below relevance floor",
            extra={"request_id": request_id, "scores": scores, "floor": settings.relevance_floor},
        )
        abstain = make_abstention_answer("No passages met the required relevance threshold.")
        response = AskResponse(
            request_id=request_id,
            answer=abstain.answer,
            citations=[],
            answered_from_context=False,
            confidence="low",
            retrieved=[
                RetrievedRef(
                    chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
                )
                for p in passages
            ],
            provider=provider.name,
        )
        # Note: never_cache rule inside cache.set ensures abstentions are not stored
        cache.set(question, response)
        return response

    # 5. Generate structured answer
    answer = provider.generate(question, passages)

    # 6. Validate citations against retrieved evidence
    grounded_answer = validate_citations(answer, passages)

    log.info(
        "answered",
        extra={
            "request_id": request_id,
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": [p.chunk_id for p in passages],
            "scores": scores,
            "answered_from_context": grounded_answer.answered_from_context,
            "citations_count": len(grounded_answer.citations),
        },
    )

    response = AskResponse(
        request_id=request_id,
        answer=grounded_answer.answer,
        citations=grounded_answer.citations,
        answered_from_context=grounded_answer.answered_from_context,
        confidence=grounded_answer.confidence,
        retrieved=[
            RetrievedRef(
                chunk_id=p.chunk_id, source=p.source, section=p.section, page=p.page, score=p.score
            )
            for p in passages
        ],
        provider=provider.name,
    )

    # 7. Store in semantic cache
    cache.set(question, response)
    return response
