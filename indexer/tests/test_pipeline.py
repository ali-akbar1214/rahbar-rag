"""Unit tests for indexer pipeline stages: extract, clean, chunk, embed, store."""

from __future__ import annotations

from pipeline.chunk import chunk
from pipeline.clean import clean
from pipeline.config import get_settings
from pipeline.embed import embed
from pipeline.models import Document, Page
from pipeline.store import store


class MockCollection:
    def __init__(self, name: str, metadata: dict) -> None:
        self.name = name
        self.metadata_dict = metadata
        self.items = {}

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        for i, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self.items[i] = (emb, doc, meta)

    def modify(self, metadata: dict) -> None:
        self.metadata_dict.update(metadata)


class MockChromaClient:
    def __init__(self) -> None:
        self.collections = {}

    def get_or_create_collection(self, name: str, metadata: dict) -> MockCollection:
        if name not in self.collections:
            self.collections[name] = MockCollection(name, metadata)
        return self.collections[name]


def test_clean_removes_repeating_headers() -> None:
    doc = Document(
        source="test.pdf",
        doc_version="2026",
        superseded=False,
        pages=[
            Page(source="test.pdf", page=1, text="FAST-NUCES Official\nSection 1\nContent A\nPage 1"),
            Page(source="test.pdf", page=2, text="FAST-NUCES Official\nSection 2\nContent B\nPage 2"),
            Page(source="test.pdf", page=3, text="FAST-NUCES Official\nSection 3\nContent C\nPage 3"),
        ],
    )
    cleaned = clean(doc)
    assert len(cleaned.pages) == 3
    # Header should be stripped
    assert "FAST-NUCES Official" not in cleaned.pages[0].text
    assert "Content A" in cleaned.pages[0].text


def test_chunk_preserves_section_and_overlap() -> None:
    doc = Document(
        source="handbook.md",
        doc_version="2026",
        superseded=False,
        pages=[
            Page(
                source="handbook.md",
                page=1,
                text="### 4.2 Prerequisite Policy\nA student who fails a prerequisite course cannot register for subsequent courses.",
            )
        ],
    )
    chunks = chunk(doc, size=100, overlap=20)
    assert len(chunks) >= 1
    c = chunks[0]
    assert "4.2 Prerequisite Policy" in c.section
    assert c.source == "handbook.md"
    assert c.doc_version == "2026"
    assert c.superseded is False


def test_embed_fallback_generates_valid_unit_vectors() -> None:
    settings = get_settings()
    texts = ["Test query 1", "Test query 2"]
    vectors = embed(texts, settings)
    assert len(vectors) == 2
    assert len(vectors[0]) == 768


def test_store_writes_chunks_and_metadata(monkeypatch) -> None:
    settings = get_settings()
    mock_client = MockChromaClient()

    import pipeline.store as store_mod
    monkeypatch.setattr(store_mod, "get_client", lambda s: mock_client)

    doc = Document(
        source="rules.md",
        doc_version="2026",
        superseded=False,
        pages=[Page(source="rules.md", page=1, text="### Attendance Rule\n80% attendance is mandatory.")],
    )
    chunks = chunk(doc, size=200, overlap=30)
    vectors = embed([c.text for c in chunks], settings)

    count = store(chunks, vectors, settings)
    assert count == len(chunks)
    col = mock_client.collections[settings.collection]
    assert col.metadata_dict["embed_model"] == settings.embed_model
    assert col.metadata_dict["dimension"] == 768
