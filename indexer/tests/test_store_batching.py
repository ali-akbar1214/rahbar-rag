"""Tests for ChromaDB store stage batch upserting."""

from __future__ import annotations

import pytest

from pipeline.config import get_settings
from pipeline.models import Chunk
from pipeline.store import store


class BatchMockCollection:
    def __init__(self) -> None:
        self.upserted_ids = []
        self.metadata = {}

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        self.upserted_ids.extend(ids)

    def modify(self, metadata) -> None:
        self.metadata.update(metadata)


class BatchMockClient:
    def __init__(self) -> None:
        self.col = BatchMockCollection()

    def get_or_create_collection(self, name, metadata):
        self.col.metadata.update(metadata)
        return self.col


def test_store_handles_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    client = BatchMockClient()

    import pipeline.store as sm
    monkeypatch.setattr(sm, "get_client", lambda s: client)

    # 300 chunks exceeds 250 batch size
    chunks = [
        Chunk(
            id=f"c-{i}",
            text=f"Text {i}",
            source="rules.pdf",
            section="General",
            page=1,
            doc_version="2026",
            superseded=False,
        )
        for i in range(300)
    ]
    vectors = [[0.1] * 768 for _ in range(300)]

    stored_count = store(chunks, vectors, settings)
    assert stored_count == 300
    assert len(client.col.upserted_ids) == 300
    assert client.col.metadata["embed_model"] == settings.embed_model
