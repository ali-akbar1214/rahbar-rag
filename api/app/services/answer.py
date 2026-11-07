"""Turns a question into an AskResponse through retrieval, caching, generation, and grounding."""

from __future__ import annotations

import logging
import time

from ..config import Settings
from ..logjson import request_id_var
from ..providers.llm.base import LLMProvider
from ..retrieval.base import Retriever
from ..routes import metrics
from ..schemas import AskResponse, RetrievedRef
from .cache import SemanticCache, is_followup_question
from .grounding import detect_injection, make_abstention_answer, sanitize_passages, validate_citations

log = logging.getLogger("rahbar.answer")
_global_cache: SemanticCache | None = None


def reset_cache() -> None:
    """Reset in-process semantic cache handle on lifespan startup."""
    global _global_cache
    _global_cache = None


def get_cache(settings: Settings) -> SemanticCache:
    global _global_cache
    if _global_cache is None or _global_cache.settings != settings:
        _global_cache = SemanticCache(settings)
    return _global_cache


def answer_question(
    question: str, retriever: Retriever, provider: LLMProvider, settings: Settings
) -> AskResponse:
    """Production query pipeline (section 3.2):
    1. Sync semantic cache generation with Chroma index version (invalidate on re-index).
    2. Check semantic cache (skipping follow-up questions).
    3. Guard against prompt injection.
    4. Retrieve top-k passages and enforce relevance floor.
    5. Sanitize untrusted retrieved passages against embedded prompt injection.
    6. Generate schema-constrained answer with retry & fallback.
    7. Validate citations against retrieved (source, section) pairs.
    8. Store in semantic cache (never-caching abstentions, follow-ups, or fallbacks).
    """
    request_id = request_id_var.get()
    cache = get_cache(settings)

    # Sync cache generation against Chroma metadata so re-indexing expires stale answers
    get_gen = getattr(retriever, "get_index_generation", None)
    if callable(get_gen):
        cache.sync_generation(get_gen())

    # 1. Semantic cache lookup (skipped for follow-up questions)
    if settings.cache_enabled and not is_followup_question(question):
        cached_resp = cache.get(question)
        if cached_resp is not None:
            metrics.record_cache_lookup(True)
            log.info(
                "answered",
                extra={
                    "request_id": request_id,
                    "retriever": retriever.name,
                    "provider": f"{provider.name} (cached)",
                    "cached": True,
                    "top_k": settings.top_k,
                    "chunk_ids": [r.chunk_id for r in cached_resp.retrieved],
                    "scores": [r.score for r in cached_resp.retrieved],
                    "abstention": not cached_resp.answered_from_context,
                    "answered_from_context": cached_resp.answered_from_context,
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
        metrics.record_cache_lookup(False)

    # 2. Guard against prompt injection in user query
    if detect_injection(question):
        metrics.ABSTENTIONS.inc()
        log.warning(
            "answered",
            extra={
                "request_id": request_id,
                "retriever": retriever.name,
                "provider": provider.name,
                "top_k": settings.top_k,
                "chunk_ids": [],
                "scores": [],
                "abstention": True,
                "answered_from_context": False,
                "reason": "prompt_injection",
            },
        )
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

    # 3. Retrieve passages and record retrieval latency
    ret_start = time.perf_counter()
    raw_passages = retriever.retrieve(question, k=settings.top_k)
    metrics.RETRIEVAL_LATENCY.observe(time.perf_counter() - ret_start)

    # Treat retrieved text as untrusted data: strip poisoned directives
    passages = sanitize_passages(raw_passages)
    scores = [round(p.score, 4) for p in passages]

    # 4. Relevance floor and honest abstention
    if not passages or max(scores) < settings.relevance_floor:
        metrics.ABSTENTIONS.inc()
        log.info(
            "answered",
            extra={
                "request_id": request_id,
                "retriever": retriever.name,
                "provider": provider.name,
                "top_k": settings.top_k,
                "chunk_ids": [p.chunk_id for p in passages],
                "scores": scores,
                "floor": settings.relevance_floor,
                "abstention": True,
                "answered_from_context": False,
            },
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
        cache.set(question, response)
        return response

    # 5. Generate structured answer and record generation latency
    gen_start = time.perf_counter()
    answer = provider.generate(question, passages)
    metrics.GENERATION_LATENCY.observe(time.perf_counter() - gen_start)

    # 6. Validate citations strictly against retrieved (source, section) evidence
    grounded_answer = validate_citations(answer, passages)
    if not grounded_answer.answered_from_context:
        metrics.ABSTENTIONS.inc()

    log.info(
        "answered",
        extra={
            "request_id": request_id,
            "retriever": retriever.name,
            "provider": provider.name,
            "top_k": settings.top_k,
            "chunk_ids": [p.chunk_id for p in passages],
            "scores": scores,
            "abstention": not grounded_answer.answered_from_context,
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

    # 7. Store in semantic cache (never-cache rules enforced inside cache.set)
    cache.set(question, response)
    return response
