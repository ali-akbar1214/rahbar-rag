"""Ollama provider with constrained decoding, retry, and safe fallback (sections 3.4 and 3.5)."""

from __future__ import annotations

import json
import logging

import httpx
from pydantic import ValidationError

from ...config import Settings
from ...schemas import Answer, Citation, Passage

log = logging.getLogger("rahbar.llm.ollama")

FALLBACK_ANSWER = Answer(
    reasoning="Fallback: Ollama generation failed or returned malformed output.",
    answer="The request could not be completed from local model inference.",
    citations=[],
    answered_from_context=False,
    confidence="low",
)


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.url = settings.ollama_url.rstrip("/")
        self.model = settings.llm_model
        self.temperature = settings.temperature

    def _build_messages(self, question: str, passages: list[Passage]) -> list[dict[str, str]]:
        context_blocks = []
        for idx, p in enumerate(passages, start=1):
            context_blocks.append(f"[{idx}] Source: {p.source} | Section: {p.section}\n{p.text}")
        context_str = "\n\n".join(context_blocks) if context_blocks else "No passages available."

        system_msg = (
            "You are RAHBAR, an official university policy Q&A assistant. "
            "You must answer strictly using the provided document passages. "
            "If the information is not present in the passages, return answered_from_context=false. "
            "Format your reply as valid JSON conforming to the Answer schema:\n"
            '{"reasoning": "string", "answer": "string", '
            '"citations": [{"source": "file.pdf", "section": "sec", "page": 1}], '
            '"answered_from_context": true, "confidence": "high" | "medium" | "low"}'
        )
        user_msg = f"Question: {question}\n\nEvidence Context:\n{context_str}"
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        """Call Ollama chat API with format='json', validate schema, retry, and fallback."""
        messages = self._build_messages(question, passages)
        endpoint = f"{self.url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": self.temperature},
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(endpoint, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data.get("message", {}).get("content", "")
                    answer = Answer.model_validate_json(content)
                    return answer
            except (ValidationError, KeyError, json.JSONDecodeError) as val_err:
                log.warning("Ollama output validation error (attempt %d): %s", attempt + 1, str(val_err))
                if attempt < max_retries:
                    continue
            except Exception as exc:
                log.error("Ollama HTTP connection error (attempt %d): %s", attempt + 1, str(exc))
                if attempt < max_retries:
                    continue

        return FALLBACK_ANSWER
