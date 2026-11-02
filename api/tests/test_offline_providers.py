"""Tests for LLM provider abstractions and offline fallbacks."""

from __future__ import annotations

from app.config import get_settings
from app.providers.llm.hosted import HostedProvider
from app.providers.llm.stub import StubProvider
from app.schemas import Passage


def test_stub_provider_cites_first_passage() -> None:
    provider = StubProvider(get_settings())
    passages = [
        Passage(chunk_id="p1", text="Text 1", source="doc1.pdf", section="1.1", page=1, score=0.9),
        Passage(chunk_id="p2", text="Text 2", source="doc2.pdf", section="1.2", page=2, score=0.8),
    ]
    ans = provider.generate("Question", passages)
    assert ans.answered_from_context is True
    assert len(ans.citations) == 1
    assert ans.citations[0].source == "doc1.pdf"


def test_hosted_provider_offline_fallback() -> None:
    # When hosted_base_url is unset, HostedProvider generates offline grounded answer
    provider = HostedProvider(get_settings())
    passages = [
        Passage(chunk_id="p1", text="Sample policy text", source="policy.pdf", section="2.1", page=3, score=0.95)
    ]
    ans = provider.generate("What is the policy?", passages)
    assert ans.answered_from_context is True
    assert ans.citations[0].source == "policy.pdf"
