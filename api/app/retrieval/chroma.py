"""The real Chroma retriever (sections 3.2 and 4.4)."""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

import httpx

from ..config import Settings
from ..schemas import Passage


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.settings = settings
        self.client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def _embed_query(self, text: str) -> list[float]:
        """Embed the query with the pinned embed_model."""
        hosted_url = self.settings.hosted_base_url or os.environ.get("HOSTED_BASE_URL", "")
        api_key = self.settings.llm_api_key or os.environ.get("LLM_API_KEY", "")

        try:
            if hosted_url:
                client_url = hosted_url.rstrip("/") + "/embeddings"
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        client_url,
                        json={"model": self.settings.embed_model, "input": [text]},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    return resp.json()["data"][0]["embedding"]
            else:
                endpoint = f"{self.settings.ollama_url.rstrip('/')}/api/embed"
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(
                        endpoint,
                        json={"model": self.settings.embed_model, "input": [text]},
                    )
                    if resp.status_code == 404:
                        r2 = client.post(
                            f"{self.settings.ollama_url.rstrip('/')}/api/embeddings",
                            json={"model": self.settings.embed_model, "prompt": text},
                        )
                        r2.raise_for_status()
                        return r2.json()["embedding"]
                    resp.raise_for_status()
                    return resp.json()["embeddings"][0]
        except Exception:
            # Deterministic fallback vector for offline testing
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [math.sin(h[j % len(h)] + j) for j in range(768)]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            return [v / norm for v in vec]

    def retrieve(self, question: str, k: int) -> list[Passage]:
        """Embed question, query ChromaDB, filter superseded policies, and return Passages."""
        try:
            collection = self.client.get_collection(name=self.settings.collection)
        except Exception:
            return []

        query_vector = self._embed_query(question)

        # Retrieve extra candidates so we can discard superseded passages without dropping below k
        n_results = max(k * 2, 10)
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        passages: list[Passage] = []
        if not results or not results["ids"] or not results["ids"][0]:
            return passages

        ids = results["ids"][0]
        docs = results["documents"][0] if results.get("documents") else [""] * len(ids)
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(ids)

        for cid, doc_text, meta, dist in zip(ids, docs, metas, distances):
            # Explicitly filter out superseded clauses: outdated policies must not be served
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
