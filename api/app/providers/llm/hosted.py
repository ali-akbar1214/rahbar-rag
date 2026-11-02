"""Hosted OpenAI-compatible LLM provider with constrained decoding, retry, and fallback."""

from __future__ import annotations

import json
import logging
import os

import httpx
from pydantic import ValidationError

from ...config import Settings
from ...schemas import Answer, Citation, Passage

log = logging.getLogger("rahbar.llm.hosted")

FALLBACK_ANSWER = Answer(
    reasoning="Fallback: upstream generation service failed or produced malformed response.",
    answer="The request could not be processed due to a temporary service degradation.",
    citations=[],
    answered_from_context=False,
    confidence="low",
)


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.hosted_base_url or os.environ.get("HOSTED_BASE_URL", "")
        self.api_key = settings.llm_api_key or os.environ.get("LLM_API_KEY", "")
        self.model = settings.llm_model
        self.temperature = settings.temperature

    def _build_prompt(self, question: str, passages: list[Passage]) -> list[dict[str, str]]:
        context_blocks = []
        for idx, p in enumerate(passages, start=1):
            context_blocks.append(
                f"[{idx}] Source: {p.source} | Section: {p.section} | Page: {p.page or 'N/A'}\n{p.text}"
            )
        context_str = "\n\n".join(context_blocks) if context_blocks else "No relevant documents found."

        system_prompt = (
            "You are RAHBAR, an official university policy Q&A assistant. "
            "You MUST answer questions strictly using the provided document excerpts. "
            "If the excerpts do not contain the answer, set answered_from_context=false and confidence='low'. "
            "Every cited document must come from the provided sources. "
            "Output JSON conforming exactly to the Answer schema:\n"
            "{\n"
            '  "reasoning": "string",\n'
            '  "answer": "string",\n'
            '  "citations": [{"source": "filename.pdf", "section": "heading", "page": 1}],\n'
            '  "answered_from_context": true,\n'
            '  "confidence": "high" | "medium" | "low"\n'
            "}"
        )

        user_content = f"Question: {question}\n\nEvidence Context:\n{context_str}"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        """Call hosted provider with constrained decoding, retry on validation failure, and safe fallback."""
        if not self.base_url:
            # When hosted_base_url is not configured (e.g. offline testing), return grounded answer directly
            if not passages:
                return Answer(
                    reasoning="No passages provided for offline hosted provider.",
                    answer="No evidence found in corpus.",
                    citations=[],
                    answered_from_context=False,
                    confidence="low",
                )
            p0 = passages[0]
            return Answer(
                reasoning=f"Answered from passage 1 ({p0.source}).",
                answer=f"According to {p0.source} ({p0.section}): {p0.text[:200]}...",
                citations=[Citation(source=p0.source, section=p0.section, page=p0.page)],
                answered_from_context=True,
                confidence="medium",
            )

        messages = self._build_prompt(question, passages)
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        # Constrained decoding requesting json_object format
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=15.0) as client:
                    resp = client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    # Validate structured model output with Pydantic
                    answer = Answer.model_validate_json(content)
                    return answer
            except (ValidationError, KeyError, json.JSONDecodeError) as val_err:
                log.warning("validation failure on attempt %d: %s", attempt + 1, str(val_err))
                if attempt < max_retries:
                    payload["temperature"] = max(0.0, self.temperature - 0.1)
                    continue
            except Exception as exc:
                log.error("hosted provider request error on attempt %d: %s", attempt + 1, str(exc))
                if attempt < max_retries:
                    continue

        log.error("all retries exhausted; returning safe fallback response")
        return FALLBACK_ANSWER
