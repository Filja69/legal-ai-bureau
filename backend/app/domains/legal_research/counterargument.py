"""CounterArgumentAgent — brief §21, "Pass 4" of multi-stage retrieval (brief
§11), run after LegalReasoner since it needs the actual conclusion to argue
against, not just the issue.

Its job is explicitly adversarial: try to prove the draft conclusion wrong.
LLM-driven query generation (TaskClass.REASONING) proposes queries aimed at
exceptions/opposing norms/contrary practice; under LLM_PROVIDER=mock this
returns nothing, so a single deterministic fallback query ("исключения" +
issue title) keeps the pass from being a no-op — it's a query *strategy*,
not invented legal content.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_research.models import EvidenceItem, LegalIssue
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.factory import build_hybrid_retriever

_COUNTER_QUERIES_SCHEMA = {
    "type": "object",
    "properties": {"counter_queries": {"type": "array"}},
}

_SYSTEM_PROMPT = (
    "Try to prove the following legal conclusion wrong. Propose Russian-language search "
    "queries that would surface: exceptions to the rule, opposing norms, contrary court "
    "practice, an alternative legal characterization, or procedural limitations. Respond "
    "via the counter_queries schema (a list of query strings).\n\n" + UNTRUSTED_CONTENT_NOTICE
)


class CounterArgumentAgent:
    def __init__(self, session: AsyncSession, llm_gateway: LLMGateway) -> None:
        self._session = session
        self._llm = llm_gateway
        self._hybrid = build_hybrid_retriever(session)

    async def find(
        self, issue: LegalIssue, conclusion: str, jurisdiction: str, effective_at: str | None, top_k: int = 5
    ) -> list[EvidenceItem]:
        queries = await self._generate_counter_queries(issue, conclusion)

        found: list[EvidenceItem] = []
        seen_chunk_ids: set[str] = set()
        for query_text in queries:
            candidates = await self._hybrid.retrieve(
                RetrievalQuery(text=query_text, jurisdiction=jurisdiction, event_date=effective_at, top_k=top_k)
            )
            for candidate in candidates:
                chunk_id = candidate.metadata.get("chunk_id", candidate.document_id)
                if chunk_id in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(chunk_id)
                found.append(
                    EvidenceItem(
                        source=candidate.metadata.get("source_id", ""),
                        citation=candidate.title,
                        text=candidate.snippet,
                        retrieval_score=candidate.score,
                        retrieval_method=candidate.metadata.get("matched_by", [candidate.retrieval_mode]),
                        chunk_id=chunk_id,
                        document_id=candidate.metadata.get("law_id") or candidate.metadata.get("court_decision_id"),
                        is_mock=bool(candidate.metadata.get("is_mock", False)),
                        issue_id=issue.id,
                        metadata=candidate.metadata,
                    )
                )
        return found

    async def _generate_counter_queries(self, issue: LegalIssue, conclusion: str) -> list[str]:
        prompt = f"{wrap_untrusted('issue', issue.title)}\n{wrap_untrusted('conclusion_to_challenge', conclusion)}"
        raw = await self._llm.structured_generate(
            TaskClass.REASONING,
            [LLMMessage(role="user", content=prompt)],
            response_schema=_COUNTER_QUERIES_SCHEMA,
            system=_SYSTEM_PROMPT,
        )
        queries = [q for q in (raw or {}).get("counter_queries") or [] if isinstance(q, str) and q.strip()]
        if not queries:
            queries = [f"исключения {issue.title}"]
        return queries
