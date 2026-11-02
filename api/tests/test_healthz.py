"""Tests for the /healthz liveness endpoint."""

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


def test_healthz_returns_ok_status(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "alive"}


def test_healthz_has_no_side_effects(client: TestClient) -> None:
    for _ in range(5):
        resp = client.get("/healthz")
        assert resp.status_code == 200
