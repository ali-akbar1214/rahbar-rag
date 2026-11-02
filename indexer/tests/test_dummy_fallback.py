"""Tests for dummy mode fallback operations."""

from __future__ import annotations

from pipeline.dummy import fake_vector


def test_fake_vector_reproducibility() -> None:
    v1 = fake_vector("Same seed")
    v2 = fake_vector("Same seed")
    assert v1 == v2
    diff = fake_vector("Different seed")
    assert v1 != diff
