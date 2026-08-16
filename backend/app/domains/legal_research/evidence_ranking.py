"""EvidenceRanker — brief §13-15. Keeps "how well did this match the query"
(retrieval_score) and "how legally authoritative is this source" (authority)
as separate signals, combined into one composite `relevance` — never
conflated, per the brief's explicit Supreme Court example.

Also enforces source diversity (brief §15): caps how many evidence items
from the same underlying document can survive ranking, so a conclusion is
never built on N near-duplicate chunks of one document.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_research.models import AUTHORITY_RANK, AuthorityLevel, EvidenceItem, EvidencePool
from app.models.case_law import Court, CourtDecision, CourtLevel

_COURT_LEVEL_TO_AUTHORITY = {
    CourtLevel.SUPREME: AuthorityLevel.SUPREME_COURT,
    CourtLevel.CASSATION: AuthorityLevel.CASSATION,
    CourtLevel.APPEAL: AuthorityLevel.APPEAL,
    CourtLevel.FIRST_INSTANCE: AuthorityLevel.FIRST_INSTANCE,
}

_MAX_PER_DOCUMENT = 2  # diversity cap — brief §15


class EvidenceRanker:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rank(self, pool: EvidencePool) -> EvidencePool:
        for item in pool.items:
            item.authority = await self._resolve_authority(item)
            item.relevance = _composite_score(item)

        pool.items.sort(key=lambda i: i.relevance, reverse=True)
        pool.items = _apply_diversity_cap(pool.items)
        return pool

    async def _resolve_authority(self, item: EvidenceItem) -> AuthorityLevel:
        if item.is_mock:
            # Mock evidence is never presented with real-world legal weight,
            # regardless of what document_type it claims to be (brief §54 of
            # Phase 2, applied here to ranking rather than just citation status).
            return AuthorityLevel.MOCK

        chunk_type = item.metadata.get("chunk_type")
        if chunk_type == "court_decision":
            court_decision_id = item.metadata.get("court_decision_id")
            if court_decision_id:
                result = await self._session.execute(
                    select(Court.level).join(CourtDecision, CourtDecision.court_id == Court.id).where(
                        CourtDecision.id == court_decision_id
                    )
                )
                level = result.scalars().first()
                if level is not None:
                    return _COURT_LEVEL_TO_AUTHORITY[level]
            return AuthorityLevel.SECONDARY_SOURCE

        if chunk_type == "law_version":
            return AuthorityLevel.CODE

        return AuthorityLevel.SECONDARY_SOURCE


def _composite_score(item: EvidenceItem) -> float:
    authority_rank = AUTHORITY_RANK.get(item.authority, 1) if item.authority else 1
    authority_component = authority_rank / max(AUTHORITY_RANK.values())

    # effective_at (as set by the retrieval pipeline) marks a value only when
    # the chunk is a superseded redaction (effective_to present) — currently
    # in-force chunks carry no upper bound, which we treat as "temporally clean".
    temporal_component = 0.8 if item.effective_at else 1.0

    return 0.5 * item.retrieval_score + 0.3 * authority_component + 0.2 * temporal_component


def _apply_diversity_cap(items: list[EvidenceItem]) -> list[EvidenceItem]:
    counts: dict[str, int] = {}
    kept: list[EvidenceItem] = []
    for item in items:
        key = item.document_id or item.chunk_id or ""
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= _MAX_PER_DOCUMENT:
            kept.append(item)
    return kept
