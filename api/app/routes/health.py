"""Liveness and readiness (sections 4.3 and 4.4).

Liveness answers: is this process responsive? (Never touches dependencies).
Readiness answers: can this pod safely serve traffic right now?
Checks Chroma connectivity, collection non-empty, Redis connectivity, and embedding-model mismatch.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Response, status

from ..config import Settings

log = logging.getLogger("rahbar.health")
router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis, or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Readiness probe verifying Chroma, non-empty collection, and embedding-model pin."""
    settings: Settings = request.app.state.settings
    checks: dict[str, object] = {}
    is_ready = True

    # If running with stubs (e.g. offline unit testing or CI fixture), report ready
    if settings.retriever == "stub":
        return {"status": "ready", "checks": {"retriever": "stub", "stub": True}}

    # 1. Check Chroma reachability and collection
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        chroma_client.heartbeat()

        collection = chroma_client.get_collection(name=settings.collection)
        chunk_count = collection.count()

        # Check collection is non-empty
        if chunk_count == 0:
            checks["chroma_collection"] = "empty: count is 0"
            is_ready = False
        else:
            checks["chroma_collection"] = f"ok ({chunk_count} chunks)"

        # 2. Embedding-model mismatch guardrail
        # Reads recorded embed_model in collection metadata and compares to current EMBED_MODEL
        meta = collection.metadata or {}
        recorded_model = meta.get("embed_model") or meta.get("embedding_model")

        if recorded_model and recorded_model != settings.embed_model:
            log.error(
                "embedding model mismatch detected: index uses %s but API configured with %s",
                recorded_model,
                settings.embed_model,
            )
            checks["embed_model"] = (
                f"embedding_model mismatch: index has {recorded_model} != configured {settings.embed_model}"
            )
            is_ready = False
        else:
            checks["embed_model"] = f"ok ({settings.embed_model})"

    except Exception as exc:
        checks["chroma"] = f"unreachable: {exc}"
        is_ready = False

    # 3. Check Redis reachability if cache enabled
    if settings.cache_enabled:
        try:
            import redis

            r = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                socket_connect_timeout=2.0,
            )
            r.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            # Redis degradation logs warning; in-memory cache acts as fallback
            checks["redis"] = f"degraded: {exc}"

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "checks": checks}

    return {"status": "ready", "checks": checks}
