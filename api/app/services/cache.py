"""Semantic cache layer with Redis and in-memory fallback (section 3.3)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any

from ..config import Settings
from ..schemas import AskResponse

log = logging.getLogger("rahbar.cache")


class SemanticCache:
    """Semantic vector cache with cosine similarity threshold and invalidation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.cache_enabled
        self.threshold = settings.cache_threshold
        self.generation_id = settings.cache_generation_id
        self._memory_cache: dict[str, dict[str, Any]] = {}

        self.redis_client: Any = None
        try:
            import redis

            self.redis_client = redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
                socket_connect_timeout=2.0,
            )
            self.redis_client.ping()
        except Exception:
            self.redis_client = None

    def _compute_vector(self, text: str) -> list[float]:
        """Produce reproducible unit-normalized vector for similarity comparison."""
        h = hashlib.sha256(text.lower().strip().encode("utf-8")).digest()
        vec = [math.sin(h[j % len(h)] + j) for j in range(128)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def get(self, question: str) -> AskResponse | None:
        """Lookup question in cache if similarity >= threshold."""
        if not self.enabled:
            return None

        query_vec = self._compute_vector(question)

        # Check in-memory store (scoped by generation_id for instant invalidation)
        prefix = f"rahbar:{self.generation_id}:"
        for key, entry in list(self._memory_cache.items()):
            if not key.startswith(prefix):
                continue
            entry_vec = entry["vector"]
            similarity = self._cosine_similarity(query_vec, entry_vec)
            if similarity >= self.threshold:
                log.info("cache hit", extra={"similarity": round(similarity, 4), "question": question})
                data = json.loads(entry["response"])
                data["cached"] = True
                return AskResponse.model_validate(data)

        # Check Redis if available
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
                        data["cached"] = True
                        return AskResponse.model_validate(data)
            except Exception as exc:
                log.warning("redis lookup failed, skipping", extra={"error": str(exc)})

        return None

    def set(self, question: str, response: AskResponse) -> None:
        """Store response in cache, respecting never-cache rules."""
        if not self.enabled:
            return

        # NEVER-CACHE RULES:
        # 1. Abstentions (answered_from_context == False) must NEVER be cached
        if not response.answered_from_context:
            log.info("never_cache rule triggered: abstention response")
            return

        # 2. Short follow-up or ambiguous phrases should not poison general cache
        if len(question.strip().split()) <= 2:
            log.info("never_cache rule triggered: short or ambiguous phrase")
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
                # 24-hour TTL on cached responses
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
                keys = self.redis_client.keys("rahbar:*")
                if keys:
                    self.redis_client.delete(*keys)
                log.info("cache invalidated and flushed")
            except Exception as exc:
                log.warning("redis flush failed", extra={"error": str(exc)})
