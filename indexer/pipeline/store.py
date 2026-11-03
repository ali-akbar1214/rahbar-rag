"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

from typing import Any

from .config import IndexerSettings
from .models import Chunk


def get_client(settings: IndexerSettings) -> Any:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count.
    """
    if not chunks:
        return 0

    client = get_client(settings)
    dimension = len(vectors[0]) if vectors and len(vectors) > 0 else 768

    # Record the embedding model pin and dimension in the collection metadata
    collection_metadata = {
        "embed_model": settings.embed_model,
        "embedding_model": settings.embed_model,
        "dimension": dimension,
        "hnsw:space": "cosine",
    }

    # Retrieve or create collection with metadata
    collection = client.get_or_create_collection(
        name=settings.collection,
        metadata=collection_metadata,
    )

    # Batch upsert into ChromaDB (max 500 records per batch)
    batch_size = 250
    total = len(chunks)

    for i in range(0, total, batch_size):
        chunk_batch = chunks[i : i + batch_size]
        vector_batch = vectors[i : i + batch_size]

        ids = [c.id for c in chunk_batch]
        documents = [c.text for c in chunk_batch]
        metadatas = [c.metadata() for c in chunk_batch]

        collection.upsert(
            ids=ids,
            embeddings=vector_batch,
            documents=documents,
            metadatas=metadatas,
        )

    # Also ensure collection metadata is updated in case collection pre-existed
    try:
        collection.modify(metadata=collection_metadata)
    except Exception:
        pass

    return total
