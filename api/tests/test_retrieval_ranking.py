"""Tests for retrieval filtering and cosine distance to similarity conversion."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.retrieval.chroma import ChromaRetriever


class MockChromaCollection:
    def query(self, query_embeddings, n_results, include):
        return {
            "ids": [["c1", "c2", "c3"]],
            "documents": [["Current policy", "Outdated policy", "Irrelevant policy"]],
            "metadatas": [[
                {"source": "rules-2026.pdf", "section": "1.1", "page": 1, "superseded": False},
                {"source": "rules-2023.pdf", "section": "1.1", "page": 1, "superseded": True},
                {"source": "other.pdf", "section": "9.9", "page": 9, "superseded": False},
            ]],
            "distances": [[0.1, 0.05, 0.85]],  # 0.1 dist -> 0.9 score, 0.85 dist -> 0.15 score (below floor)
        }


class MockChromaClient:
    def get_collection(self, name: str):
        return MockChromaCollection()


def test_chroma_retriever_filters_superseded_and_converts_similarity(monkeypatch: pytest.MonkeyPatch) -> None:
    import chromadb
    monkeypatch.setattr(chromadb, "HttpClient", lambda **kwargs: MockChromaClient())
    settings = get_settings()
    retriever = ChromaRetriever(settings)

    passages = retriever.retrieve("What is the rule?", k=5)
    # c2 is superseded -> excluded
    # c3 score is 1 - 0.85 = 0.15 < relevance_floor (0.35) -> excluded
    assert len(passages) == 1
    assert passages[0].chunk_id == "c1"
    assert passages[0].score == 0.9
    assert passages[0].source == "rules-2026.pdf"
