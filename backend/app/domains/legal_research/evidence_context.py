"""LegalEvidenceContext — what actually gets handed to an LLM (brief §31-32).

Built from HybridRetriever candidates, each re-verified through
CitationValidator before being admitted. This is the mechanism behind
LEGAL-RAG.md's rule: the model reasons over *this* object, never over
"what it remembers" about Russian law. If no candidate survives
verification, `sources` is empty and `status` is SOURCE_NOT_FOUND — the
caller (Research API / an agent, once built) must not paper over that with
a fabricated answer (brief §32).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.retrieval.base import RetrievedCandidate
from app.rag.validation.citation_validator import CitationDraft, CitationStatus, CitationValidator

_ADMISSIBLE_STATUSES = {CitationStatus.VERIFIED, CitationStatus.MOCK}


@dataclass
class EvidenceSource:
    citation: str
    text: str
    source_url: str | None
    verified: bool
    status: CitationStatus
    is_mock: bool


@dataclass
class LegalEvidenceContext:
    question: str
    effective_at: date | None
    sources: list[EvidenceSource] = field(default_factory=list)
    status: str = "ok"  # "ok" | "source_not_found"


async def build_evidence_context(
    session: AsyncSession,
    question: str,
    candidates: list[RetrievedCandidate],
    effective_at: date | None = None,
) -> LegalEvidenceContext:
    validator = CitationValidator(session)
    sources: list[EvidenceSource] = []

    for candidate in candidates:
        if candidate.metadata.get("chunk_type") != "law_version":
            # Court-decision candidates aren't citation-checked against
            # LawVersion — they're evidence in their own right, admitted as-is
            # with verified=False until a CourtDecision-specific check exists.
            sources.append(
                EvidenceSource(
                    citation=candidate.title,
                    text=candidate.snippet,
                    source_url=None,
                    verified=False,
                    status=CitationStatus.UNVERIFIED,
                    is_mock=bool(candidate.metadata.get("is_mock", False)),
                )
            )
            continue

        draft = CitationDraft(
            law_short_name=None,
            article_number=candidate.metadata.get("article_number"),
            quoted_fragment=None,  # candidate.snippet is a truncated excerpt, not a verbatim claim to check
            event_date=effective_at,
        )
        check = await validator.validate(draft)
        if check.status not in _ADMISSIBLE_STATUSES:
            continue

        sources.append(
            EvidenceSource(
                citation=candidate.title,
                text=candidate.snippet,
                source_url=None,
                verified=check.status == CitationStatus.VERIFIED,
                status=check.status,
                is_mock=check.status == CitationStatus.MOCK,
            )
        )

    status = "ok" if sources else "source_not_found"
    return LegalEvidenceContext(question=question, effective_at=effective_at, sources=sources, status=status)


SOURCE_NOT_FOUND_MESSAGE = (
    "Не удалось найти подтвержденную норму права для данного вывода в подключенных источниках."
)
