"""LegalQueryGenerator — brief §9-10.

Never sends the raw user question straight to search. LLM-driven
(TaskClass.RESEARCH) generation of several typed queries per issue. Under
LLM_PROVIDER=mock this yields nothing, so a single LAW-type fallback query
(the issue title itself) keeps the pipeline from dead-ending — still real
retrieval, just without the multi-angle query expansion a real model would add.
"""
from __future__ import annotations

from app.domains.legal_research.models import LegalIssue, QueryType, ResearchQuery
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass

_QUERIES_SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array"}},
}

_SYSTEM_PROMPT = (
    "You generate Russian-language search queries for a legal knowledge base, given one "
    "legal issue. Produce several short queries covering: the applicable law, court "
    "practice, official legal positions, counterarguments, definitions, and procedure as "
    "relevant. Classify each with query_type: law, court_practice, legal_position, "
    "counterargument, definition, procedural. Respond via the queries schema.\n\n" + UNTRUSTED_CONTENT_NOTICE
)

_VALID_TYPES = {t.value for t in QueryType}


class LegalQueryGenerator:
    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def generate(self, issue: LegalIssue) -> list[ResearchQuery]:
        prompt = f"{wrap_untrusted('issue_title', issue.title)}\n{wrap_untrusted('issue_description', issue.description)}"
        raw = await self._llm.structured_generate(
            TaskClass.RESEARCH,
            [LLMMessage(role="user", content=prompt)],
            response_schema=_QUERIES_SCHEMA,
            system=_SYSTEM_PROMPT,
        )
        entries = (raw or {}).get("queries") or []

        queries: list[ResearchQuery] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("text"):
                continue
            query_type_raw = entry.get("query_type", "law")
            query_type = QueryType(query_type_raw) if query_type_raw in _VALID_TYPES else QueryType.LAW
            queries.append(ResearchQuery(text=entry["text"], query_type=query_type, issue_id=issue.id))

        if not queries:
            queries.append(ResearchQuery(text=issue.title, query_type=QueryType.LAW, issue_id=issue.id))
        return queries
