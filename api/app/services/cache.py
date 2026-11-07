"""Semantic cache layer with Redis and in-memory fallback (section 3.3)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from typing import Any

from ..config import Settings
from ..retrieval.chroma import embed_query_text
from ..schemas import AskResponse

log = logging.getLogger("rahbar.cache")

_FOLLOWUP_PREFIX_RE = re.compile(
    r"^(?:and\b|also\b|what\s+about\b|how\s+about\b|or\s+what\s+if\b|then\s+can\b|so\s+can\b|"
    r"what\s+if\s+(?:i|they|he|she|we)\b|does\s+(?:it|that|this)\b|is\s+(?:it|that|this)\b|"
    r"can\s+(?:i|we)\s+(?:do|repeat|take|drop)\s+(?:it|that|them|those)\b)",
    re.IGNORECASE,
)
_FOLLOWUP_ANAPHORA_RE = re.compile(
    r"\b(?:that\s+rule|that\s+clause|that\s+policy|same\s+course|previous\s+question|above\s+policy)\b",
    re.IGNORECASE,
)


def is_followup_question(question: str) -> bool:
    """Detect conversational follow-ups that depend on prior turn context (sections 3.2 & 3.3)."""
    cleaned = question.strip()
    if len(cleaned.split()) <= 2:
        return True
    if _FOLLOWUP_PREFIX_RE.search(cleaned) or _FOLLOWUP_ANAPHORA_RE.search(cleaned):
        return True
    return False


class SemanticCache:
    """Semantic vector cache using the pinned embedding model, cosine threshold, and invalidation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.cache_enabled
        self.threshold = settings.cache_threshold
        self.generation_id = settings.cache_generation_id
        self._memory_cache: dict[str, dict[str, Any]] = {}

        self.redis_client: Any = None
        if self.enabled:
            try:
                import redis

                self.redis_client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                )
                self.redis_client.ping()
            except Exception:
                self.redis_client = None

    def _compute_vector(self, text: str) -> list[float]:
        """Embed query using the pinned `EMBED_MODEL` and normalize to unit length."""
        vec = embed_query_text(text, self.settings)
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        return sum(x * y for x, y in zip(a, b))

    def sync_generation(self, index_generation: str | None) -> None:
        """Expire cached entries automatically whenever the indexer Job writes a new index generation."""
        if not index_generation:
            return
        if self.redis_client:
            try:
                recorded = self.redis_client.get("rahbar:active_generation")
                if recorded != index_generation:
                    self.invalidate(index_generation)
                    self.redis_client.set("rahbar:active_generation", index_generation)
                    return
            except Exception:
                pass
        if self.generation_id != index_generation:
            self.invalidate(index_generation)

    def get(self, question: str) -> AskResponse | None:
        """Lookup question in semantic cache if similarity >= threshold; skip follow-up questions."""
        if not self.enabled:
            return None

        if is_followup_question(question):
            log.info("skip_cache lookup: follow-up question detected", extra={"question": question})
            return None

        query_vec = self._compute_vector(question)
        prefix = f"rahbar:{self.generation_id}:"

        # Check Redis first when available (shared across all API replicas)
        if self.redis_client:
            try:
                keys = self.redis_client.keys(f"{prefix}*")
                for k in keys:
                    val = self.redis_client.get(k)
                    if not val:
                        continue
                    entry = json.loads(val)
                    similarity = self._cosine_similarity(query_vec, entry["vector"])
                    if similarity >= self.threshold:
                        log.info("redis cache hit", extra={"similarity": round(similarity, 4)})
                        data = json.loads(entry["response"])
                        return AskResponse.model_validate(data)
            except Exception as exc:
                log.warning("redis lookup failed, checking local fallback", extra={"error": str(exc)})

        # In-memory fallback (for offline unit tests)
        for key, entry in list(self._memory_cache.items()):
            if not key.startswith(prefix):
                continue
            entry_vec = entry["vector"]
            similarity = self._cosine_similarity(query_vec, entry_vec)
            if similarity >= self.threshold:
                log.info("cache hit", extra={"similarity": round(similarity, 4), "question": question})
                data = json.loads(entry["response"])
                return AskResponse.model_validate(data)

        return None

    def set(self, question: str, response: AskResponse) -> None:
        """Store response in semantic cache, enforcing strict never-cache guardrails."""
        if not self.enabled:
            return

        # NEVER-CACHE RULES (section 3.3):
        # 1. Abstentions, out-of-scope answers, or validation fallbacks (answered_from_context == False)
        if not response.answered_from_context or "fallback" in response.provider.lower():
            log.info("never_cache rule triggered: abstention or fallback response")
            return

        # 2. Follow-up or ambiguous questions must never be cached
        if is_followup_question(question):
            log.info("never_cache rule triggered: follow-up or ambiguous question")
            return

        query_vec = self._compute_vector(question)
        prefix = f"rahbar:{self.generation_id}:"
        q_hash = hashlib.sha256(question.lower().strip().encode("utf-8")).hexdigest()[:16]
        cache_key = f"{prefix}{q_hash}"

        payload = {
            "question": question,
            "vector": query_vec,
            "response": response.model_dump_json(),
        }

        self._memory_cache[cache_key] = payload

        if self.redis_client:
            try:
                self.redis_client.setex(cache_key, 86400, json.dumps(payload))
            except Exception as exc:
                log.warning("redis set failed", extra={"error": str(exc)})

    def invalidate(self, new_generation_id: str | None = None) -> None:
        """Invalidate all cached items after a re-indexing Job."""
        if new_generation_id:
            self.generation_id = new_generation_id
        self._memory_cache.clear()
        if self.redis_client:
            try:
                keys = [k for k in self.redis_client.keys("rahbar:*") if k != "rahbar:active_generation"]
                if keys:
                    self.redis_client.delete(*keys)
                log.info("cache invalidated and flushed", extra={"generation_id": self.generation_id})
            except Exception as exc:
                log.warning("redis flush failed", extra={"error": str(exc)})
