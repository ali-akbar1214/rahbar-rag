"""Tests for API error handling on malformed JSON and missing parameters."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    with TestClient(app) as c:
        yield c


def test_missing_question_returns_422(client: TestClient) -> None:
    resp = client.post("/api/ask", json={})
    assert resp.status_code == 422


def test_null_question_returns_422(client: TestClient) -> None:
    resp = client.post("/api/ask", json={"question": None})
    assert resp.status_code == 422
