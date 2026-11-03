"""Prometheus metrics at /metrics (section 4.8).

Request count and latency are wired up already. Add your own the same way:
retrieval latency, generation latency, cache hits, abstentions, fallbacks, tokens.
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

router = APIRouter()

REQUESTS = Counter("rahbar_requests_total", "HTTP requests", ["path", "status"])
LATENCY = Histogram(
    "rahbar_request_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
REQUEST_LATENCY = Histogram(
    "rahbar_request_latency_seconds",
    "HTTP request latency",
    ["path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
RETRIEVAL_LATENCY = Histogram(
    "rahbar_retrieval_latency_seconds",
    "Retrieval latency",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
GENERATION_LATENCY = Histogram(
    "rahbar_generation_latency_seconds",
    "LLM generation latency",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20),
)
CACHE_HITS = Counter("rahbar_cache_hits_total", "Total semantic cache hits")
CACHE_MISSES = Counter("rahbar_cache_misses_total", "Total semantic cache misses")
ABSTENTIONS = Counter("rahbar_abstentions_total", "Total honest abstentions")
FALLBACKS = Counter("rahbar_fallbacks_total", "Total generation fallbacks")
TOKENS_IN = Counter("rahbar_tokens_in_total", "Prompt input tokens")
TOKENS_OUT = Counter("rahbar_tokens_out_total", "Generated output tokens")


@router.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
