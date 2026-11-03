"""Tests for Prometheus metrics endpoints and latency observation."""

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


def test_metrics_endpoint_scraping(client: TestClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "rahbar_requests_total" in resp.text
    assert "rahbar_request_latency_seconds" in resp.text
