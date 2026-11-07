"""Tests for the /readyz readiness endpoint and embedding model guardrail."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_readyz_stub_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVER", "stub")
    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


def test_readyz_model_mismatch_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockCollectionMismatch:
        metadata = {"embed_model": "old-model-v1"}
        def count(self) -> int:
            return 100

    class MockChromaClient:
        def heartbeat(self) -> None:
            pass
        def get_collection(self, name: str):
            return MockCollectionMismatch()

    monkeypatch.setenv("RETRIEVER", "chroma")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("CACHE_ENABLED", "false")

    import chromadb
    monkeypatch.setattr(chromadb, "HttpClient", lambda **kwargs: MockChromaClient())

    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "embedding_model mismatch" in str(data["checks"]["embed_model"])


def test_readyz_redis_unreachable_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class MockHealthyCollection:
        metadata = {"embed_model": "nomic-embed-text", "dimension": 768}

        def count(self) -> int:
            return 42

    class MockHealthyChroma:
        def heartbeat(self) -> None:
            pass

        def get_collection(self, name: str) -> MockHealthyCollection:
            return MockHealthyCollection()

    class BrokenRedis:
        def ping(self) -> None:
            raise ConnectionError("redis connection refused")

    monkeypatch.setenv("RETRIEVER", "chroma")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("CACHE_ENABLED", "true")

    import chromadb
    import redis

    monkeypatch.setattr(chromadb, "HttpClient", lambda **kwargs: MockHealthyChroma())
    monkeypatch.setattr(redis, "Redis", lambda **kwargs: BrokenRedis())

    with TestClient(app) as client:
        resp = client.get("/readyz")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "unreachable" in str(data["checks"]["redis"])
