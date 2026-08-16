"""FactExtractor — first stage of the Research Engine (brief §4-6).

User-supplied facts are trusted as-is (FactOrigin.USER_STATED, confidence
1.0) — no LLM roundtrip needed to know what the user already told us.
Additional facts/missing-fact gaps are extracted via LLMGateway
(TaskClass.EXTRACTION) with a fixed JSON schema. Under LLM_PROVIDER=mock
this legitimately returns nothing (MockLLMProvider's schema-driven empty
defaults) — the pipeline must still work correctly with zero AI-inferred
facts, since user-stated facts alone are enough to proceed.
"""
from __future__ import annotations

from app.domains.legal_research.models import Criticality, FactOrigin, LegalFact, MissingFact
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass

_MISSING_FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "missing_facts": {"type": "array"},
    },
}

_SYSTEM_PROMPT = (
    "You identify only the legally material facts required to answer a Russian-law "
    "question. Never invent facts that were not stated. Return only what is asked for "
    "in the JSON schema.\n\n" + UNTRUSTED_CONTENT_NOTICE
)


class FactExtractor:
    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def extract(self, question: str, user_facts: list[str]) -> tuple[list[LegalFact], list[MissingFact]]:
        facts = [
            LegalFact(subject="", predicate=text, source=FactOrigin.USER_STATED, confidence=1.0)
            for text in user_facts
        ]

        missing = await self._identify_missing_facts(question, user_facts)
        return facts, missing

    async def _identify_missing_facts(self, question: str, user_facts: list[str]) -> list[MissingFact]:
        prompt = (
            f"{wrap_untrusted('question', question)}\n"
            f"{wrap_untrusted('known_facts', str(user_facts) if user_facts else '(none provided)')}\n\n"
            "List only facts that are CRITICALLY necessary to answer the question and are "
            "currently unknown. Classify each as critical/important/optional. Respond via the "
            "missing_facts schema."
        )
        raw = await self._llm.structured_generate(
            TaskClass.EXTRACTION,
            [LLMMessage(role="user", content=prompt)],
            response_schema=_MISSING_FACTS_SCHEMA,
            system=_SYSTEM_PROMPT,
        )
        entries = (raw or {}).get("missing_facts") or []

        results: list[MissingFact] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("question"):
                continue
            try:
                criticality = Criticality(entry.get("criticality", "optional"))
            except ValueError:
                criticality = Criticality.OPTIONAL
            results.append(MissingFact(question=entry["question"], criticality=criticality, reason=entry.get("reason", "")))
        return results
