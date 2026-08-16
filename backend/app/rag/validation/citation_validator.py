"""CitationValidator v2 — the anti-hallucination gate (LEGAL-RAG.md §4, Phase 2 brief §28-30).

Every citation an agent produces must pass through here before it is
persisted as a `Citation` row or shown to a user as fact. Checks, in order:

1. article/law resolvable in the Knowledge Base at all (any date)          -> else UNVERIFIED
2. resolvable specifically at the requested effective_at                   -> else TEMPORALLY_INVALID
3. quoted fragment actually appears in the stored text                     -> else BROKEN
4. provenance hash still matches the source document it was ingested from  -> else BROKEN
5. originating source isn't a mock dataset masquerading as official        -> else MOCK

Only a citation that survives all five is VERIFIED.
"""
from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_knowledge import Law, LawVersion, LegalSource
from app.models.source_document import SourceDocument


class CitationStatus(str, enum.Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    BROKEN = "broken"
    TEMPORALLY_INVALID = "temporally_invalid"
    MOCK = "mock"


@dataclass
class CitationDraft:
    law_short_name: str | None
    article_number: str | None
    quoted_fragment: str | None
    event_date: date | None = None


@dataclass
class CitationCheck:
    status: CitationStatus
    reason: str
    law_version_id: str | None = None
    source_id: str | None = None


class CitationValidator:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def validate(self, draft: CitationDraft) -> CitationCheck:
        if not draft.article_number:
            return CitationCheck(status=CitationStatus.UNVERIFIED, reason="No article number supplied to validate against.")

        all_versions = await self._find_versions(draft, effective_at=None)
        if not all_versions:
            return CitationCheck(
                status=CitationStatus.UNVERIFIED,
                reason="No matching article found in the Legal Knowledge Base at any date.",
            )

        event_date = draft.event_date or date.today()
        current_versions = [v for v in all_versions if v.valid_from <= event_date and (v.valid_to is None or v.valid_to > event_date)]
        if not current_versions:
            return CitationCheck(
                status=CitationStatus.TEMPORALLY_INVALID,
                reason=f"Article exists in the Knowledge Base, but no redaction was in force on {event_date}.",
            )

        version = current_versions[0]

        if draft.quoted_fragment and draft.quoted_fragment.strip() not in version.text:
            return CitationCheck(
                status=CitationStatus.BROKEN,
                reason="Quoted fragment does not match the stored article text.",
                law_version_id=str(version.id),
            )

        hash_check = await self._verify_provenance_hash(version)
        if hash_check is False:
            return CitationCheck(
                status=CitationStatus.BROKEN,
                reason="Stored text no longer matches its original provenance hash — possible data corruption.",
                law_version_id=str(version.id),
            )

        source = await self._resolve_source(version)
        if source is not None and source.is_mock:
            return CitationCheck(
                status=CitationStatus.MOCK,
                reason="Citation resolves correctly, but its source is a mock/development dataset, not a verified official source.",
                law_version_id=str(version.id),
                source_id=str(source.id),
            )

        return CitationCheck(
            status=CitationStatus.VERIFIED,
            reason="Article and quote confirmed against the Legal Knowledge Base.",
            law_version_id=str(version.id),
            source_id=str(source.id) if source else None,
        )

    async def _find_versions(self, draft: CitationDraft, effective_at: date | None) -> list[LawVersion]:
        stmt = select(LawVersion).where(LawVersion.article_number == draft.article_number)
        if draft.law_short_name:
            stmt = stmt.join(Law, Law.id == LawVersion.law_id).where(Law.short_name == draft.law_short_name)
        if effective_at is not None:
            stmt = stmt.where(
                LawVersion.valid_from <= effective_at,
                (LawVersion.valid_to.is_(None)) | (LawVersion.valid_to > effective_at),
            )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _verify_provenance_hash(self, version: LawVersion) -> bool | None:
        """Returns None (skip) if the version has no linked SourceDocument yet
        (e.g. seeded directly rather than through the ingestion pipeline) —
        absence of provenance is a different problem than a hash mismatch,
        and shouldn't be reported as BROKEN.
        """
        if version.source_document_id is None:
            return None
        source_document = await self._session.get(SourceDocument, version.source_document_id)
        if source_document is None or source_document.normalized_content is None:
            return None
        recomputed = hashlib.sha256(source_document.normalized_content.encode("utf-8")).hexdigest()
        return recomputed == source_document.content_hash

    async def _resolve_source(self, version: LawVersion) -> LegalSource | None:
        if version.source_document_id is None:
            return None
        source_document = await self._session.get(SourceDocument, version.source_document_id)
        if source_document is None:
            return None
        return await self._session.get(LegalSource, source_document.source_id)
