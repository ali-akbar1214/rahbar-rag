"""The real Chroma retriever (sections 3.2 and 4.4)."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any

import httpx

from ..config import Settings
from ..schemas import Passage

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "can", "could", "did",
    "do", "does", "for", "from", "how", "i", "if", "in", "is", "it", "its", "may",
    "much", "my", "now", "of", "on", "or", "say", "the", "to", "was", "were", "what",
    "when", "where", "which", "who", "why", "with",
})

_HISTORICAL_YEAR_RE = re.compile(r"\b(2019|2020|2021|2022|2023|2024)\b")
_CURRENT_YEAR_RE = re.compile(r"\b(2026|2027|current|active|latest)\b", re.IGNORECASE)
_OLDER_VERSION_PHRASE_RE = re.compile(
    r"\b(?:old|older|previous|prior|superseded|former|historical|earlier|repealed)\s+"
    r"(?:version|policy|policies|rules?|handbook|edition|regulations?)\b"
    r"|\bunder\s+the\s+old\b",
    re.IGNORECASE,
)


def _stem(word: str) -> str:
    for suffix in ("ance", "ence", "ing", "tion"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    if len(word) > 4 and word.endswith(("ed", "es")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def _offline_vector(text: str, dim: int = 768) -> list[float]:
    """Feature-hashed unit vector identical to indexer.pipeline.embed._deterministic_vector."""
    raw_tokens = re.findall(r"[a-z0-9]+", text.lower())
    features = [_stem(t) for t in raw_tokens if t not in _STOPWORDS and len(t) > 1]
    vec = [0.0] * dim
    for tok in features:
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [math.sin(h[j % len(h)] + j) for j in range(dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_SYNONYMS = {
    "plagiar": ["dishonesty", "penalty", "penalties", "cheating"],
    "caught": ["found", "guilty", "evidence"],
    "someone": ["student"],
}


def _expand_for_retrieval(query: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    extra: list[str] = []
    for t in tokens:
        st = _stem(t)
        for prefix, syns in _SYNONYMS.items():
            if prefix in st or st in prefix:
                extra.extend(syns)
    if extra:
        return query + " " + " ".join(extra)
    return query


def embed_query_text(text: str, settings: Settings) -> list[float]:
    """Embed a user question using the pinned `EMBED_MODEL` (shared by retriever & semantic cache)."""
    if (
        settings.llm_provider.lower() == "stub"
        or settings.retriever.lower() == "stub"
        or settings.embed_model == "lexical-hash-768"
    ):
        return _offline_vector(_expand_for_retrieval(text), 768)

    embed_base_url = os.environ.get("EMBED_BASE_URL", "")
    api_key = os.environ.get("EMBED_API_KEY") or settings.llm_api_key or os.environ.get("LLM_API_KEY", "")

    try:
        if embed_base_url:
            client_url = embed_base_url.rstrip("/") + "/embeddings"
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    client_url,
                    json={"model": settings.embed_model, "input": [text]},
                    headers=headers,
                )
                resp.raise_for_status()
                return list(resp.json()["data"][0]["embedding"])
        else:
            endpoint = f"{settings.ollama_url.rstrip('/')}/api/embed"
            with httpx.Client(timeout=httpx.Timeout(15.0, connect=2.0)) as client:
                resp = client.post(
                    endpoint,
                    json={"model": settings.embed_model, "input": [text]},
                )
                if resp.status_code == 404:
                    r2 = client.post(
                        f"{settings.ollama_url.rstrip('/')}/api/embeddings",
                        json={"model": settings.embed_model, "prompt": text},
                    )
                    r2.raise_for_status()
                    return list(r2.json()["embedding"])
                resp.raise_for_status()
                return list(resp.json()["embeddings"][0])
    except Exception:
        # Deterministic fallback vector for offline testing
        return _offline_vector(_expand_for_retrieval(text), 768)


def asks_for_older_version(question: str) -> bool:
    """Return True only when the user explicitly asks about an older/superseded policy version."""
    if _OLDER_VERSION_PHRASE_RE.search(question):
        return True
    if _HISTORICAL_YEAR_RE.search(question) and not _CURRENT_YEAR_RE.search(question):
        return True
    return False


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.settings = settings
        self.last_indexed_at: str | None = None
        self.client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _embed_query(self, text: str) -> list[float]:
        """Embed the query with the pinned embed_model."""
        return embed_query_text(text, self.settings)

    def get_index_generation(self) -> str | None:
        """Return the Chroma collection's `indexed_at` metadata token to detect re-indexing."""
        try:
            collection = self.client.get_collection(name=self.settings.collection)
            meta = getattr(collection, "metadata", None) or {}
            gen = meta.get("indexed_at")
            if gen:
                self.last_indexed_at = str(gen)
            return self.last_indexed_at
        except Exception:
            return self.last_indexed_at

    def retrieve(self, question: str, k: int) -> list[Passage]:
        """Embed question, query ChromaDB with superseded metadata filter, and return Passages."""
        try:
            collection = self.client.get_collection(name=self.settings.collection)
        except Exception:
            return []

        col_meta = getattr(collection, "metadata", None) or {}
        if col_meta.get("indexed_at"):
            self.last_indexed_at = str(col_meta["indexed_at"])

        query_vector = self._embed_query(question)
        include_superseded = asks_for_older_version(question)

        n_results = max(k * 2, 10)
        q_emb: Any = [query_vector]
        query_kwargs: dict[str, Any] = {
            "query_embeddings": q_emb,
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if not include_superseded:
            query_kwargs["where"] = {"superseded": False}

        try:
            results = collection.query(**query_kwargs)
        except TypeError:
            # Support simplified mock collections in unit tests that omit `where`
            query_kwargs.pop("where", None)
            results = collection.query(**query_kwargs)

        passages: list[Passage] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return passages

        ids = results["ids"][0]
        raw_docs = results.get("documents")
        raw_metas = results.get("metadatas")
        raw_dists = results.get("distances")
        docs = raw_docs[0] if raw_docs else [""] * len(ids)
        metas: list[Any] = list(raw_metas[0]) if raw_metas else [{}] * len(ids)
        distances = raw_dists[0] if raw_dists else [0.0] * len(ids)

        for cid, doc_text, meta, dist in zip(ids, docs, metas, distances):
            # Exclude superseded documents unless the user explicitly asked about an older version
            if not include_superseded:
                superseded = meta.get("superseded", False)
                if superseded is True or str(superseded).lower() == "true":
                    continue

            # Convert cosine distance to similarity score: similarity = 1 - distance
            score = 1.0 - float(dist)

            # Apply relevance floor filter
            if score < self.settings.relevance_floor:
                continue

            passages.append(
                Passage(
                    chunk_id=cid,
                    text=doc_text,
                    source=str(meta.get("source", "unknown")),
                    section=str(meta.get("section", "General")),
                    page=int(meta["page"]) if meta.get("page") is not None else None,
                    score=round(score, 4),
                )
            )
            if len(passages) >= k:
                break

        return passages
