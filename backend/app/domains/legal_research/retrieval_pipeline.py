"""MultiStageRetriever — brief §11-12. Reuses the existing HybridRetriever
(app/rag/retrieval — Phase 2) unchanged; this module only sequences multiple
passes over it and folds results into an EvidencePool. It does not
reimplement retrieval.

Pass 1 Primary Law -> document_type=law_article
Pass 2 Interpretation -> document_type=interpretation (honestly empty today —
        the Phase 2 mock dataset has no `interpretation` documents; this pass
        exists structurally for when real official explanations are ingested)
Pass 3 Court Practice -> document_type=court_decision
Pass 5 Fact-specific -> unfiltered, driven by the user's stated facts

Pass 4 (Counterargument) lives in app/domains/legal_research/counterargument.py
since it needs the *conclusion* of reasoning to search against, not just the
issue — it runs after LegalReasoner, not as part of this initial sweep.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_research.models import EvidenceItem, EvidencePool, QueryType, ResearchQuery
from app.rag.retrieval.base import RetrievalQuery, RetrievedCandidate
from app.rag.retrieval.factory import build_hybrid_retriever


class MultiStageRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._hybrid = build_hybrid_retriever(session)

    async def run(
        self, queries: list[ResearchQuery], jurisdiction: str, effective_at: str | None, facts: list[str], top_k_per_query: int = 15
    ) -> EvidencePool:
        pool = EvidencePool()
        seen_chunk_ids: set[str] = set()

        for query in queries:
            document_type = _document_type_for(query.query_type)
            candidates = await self._hybrid.retrieve(
                RetrievalQuery(
                    text=query.text, jurisdiction=jurisdiction, event_date=effective_at,
                    filters={"document_type": document_type} if document_type else {}, top_k=top_k_per_query,
                )
            )
            _merge(pool, candidates, seen_chunk_ids, issue_id=query.issue_id)

        if facts:
            fact_query = RetrievalQuery(
                text=" ".join(facts), jurisdiction=jurisdiction, event_date=effective_at, top_k=top_k_per_query
            )
            candidates = await self._hybrid.retrieve(fact_query)
            _merge(pool, candidates, seen_chunk_ids)

        return pool


def _document_type_for(query_type: QueryType) -> str | None:
    return {
        QueryType.LAW: "law_article",
        QueryType.COURT_PRACTICE: "court_decision",
        QueryType.LEGAL_POSITION: "interpretation",
    }.get(query_type)


def _merge(
    pool: EvidencePool, candidates: list[RetrievedCandidate], seen_chunk_ids: set[str], issue_id: str | None = None
) -> None:
    for candidate in candidates:
        chunk_id = candidate.metadata.get("chunk_id", candidate.document_id)
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)

        document_id = candidate.metadata.get("law_id") or candidate.metadata.get("court_decision_id") or candidate.document_id
        pool.items.append(
            EvidenceItem(
                source=candidate.metadata.get("source_id", ""),
                citation=candidate.title,
                text=candidate.snippet,
                retrieval_score=candidate.score,
                retrieval_method=candidate.metadata.get("matched_by", [candidate.retrieval_mode]),
                authority=None,  # filled by EvidenceRanker, which knows how to resolve court level
                effective_at=candidate.metadata.get("effective_to") or candidate.metadata.get("effective_from"),
                chunk_id=chunk_id,
                document_id=document_id,
                is_mock=bool(candidate.metadata.get("is_mock", False)),
                issue_id=issue_id,
                metadata=candidate.metadata,
            )
        )
