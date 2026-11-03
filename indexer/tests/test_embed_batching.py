"""Tests for embedding batching and vector normalization."""

from __future__ import annotations

import math

from pipeline.config import get_settings
from pipeline.embed import _deterministic_vector, embed


def test_deterministic_vector_dimension_and_norm() -> None:
    vec = _deterministic_vector("FAST-NUCES CS Policy", dim=768)
    assert len(vec) == 768
    # Norm must equal 1.0 (unit vector)
    norm = math.sqrt(sum(v * v for v in vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-6)


def test_embed_batch_processing() -> None:
    settings = get_settings()
    # Batch of 40 items exceeds batch_size (32)
    texts = [f"Clause text number {i}" for i in range(40)]
    vectors = embed(texts, settings)
    assert len(vectors) == 40
    for v in vectors:
        assert len(v) == 768
