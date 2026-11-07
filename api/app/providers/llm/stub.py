"""A provider with no model and no network.

Use it for every unit test and for CI (section 6): your tests must never call a
real model. It is deterministic: the same input always gives the same output.
"""

from __future__ import annotations

from ...routes import metrics
from ...schemas import Answer, Citation, Passage


class StubProvider:
    name = "stub"

    def __init__(self, settings=None) -> None:
        self.settings = settings

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        if not passages:
            return Answer(
                reasoning="stub: nothing was retrieved",
                answer="(stub) No passages were retrieved for this question.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )
        top = passages[0]
        ans_text = (
            f"(stub) A model would answer here from {len(passages)} passages. "
            f"The first one [{top.source} / {top.section}] says: {top.text}"
        )
        metrics.TOKENS_IN.inc(max(1, len(question.split()) + sum(len(p.text.split()) for p in passages)))
        metrics.TOKENS_OUT.inc(max(1, len(ans_text.split())))
        return Answer(
            reasoning="stub: cites the first retrieved passage",
            answer=ans_text,
            citations=[Citation(source=top.source, section=top.section, page=top.page)],
            answered_from_context=True,
            confidence="low",
        )
