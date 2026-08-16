"""IngestionPipeline — generic lifecycle, source-agnostic (LEGAL-SOURCES.md §2/§11).

```
discover -> fetch -> parse -> normalize -> validate -> hash -> deduplicate -> persist -> index
```

Nothing here knows about `OfficialLawSource`, `MockLegalDataSource`, etc. —
it depends only on `LegalDataSource` (fetch/search/sync) plus a
`SourceParser`/`SourceNormalizer`/`SourceValidator` triple registered for
that source's format. Adding a new source never touches this file.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_knowledge.ingestion.hashing import content_hash
from app.domains.legal_knowledge.ingestion.protocols import (
    LegalIndexer,
    ParsedLegalContent,
    SourceNormalizer,
    SourceParser,
    SourceValidator,
)
from app.domains.legal_knowledge.temporal_resolver import TemporalLawResolver
from app.models.case_law import Court, CourtDecision, CourtLevel
from app.models.legal_knowledge import Law, LawVersion, LegalDocument, LegalDocumentType, LegalSource
from app.models.source_document import SourceDocument
from app.sources.base import LegalDataSource, SourceQuery


class IngestionValidationError(Exception):
    pass


@dataclass
class IngestResult:
    external_id: str
    skipped: bool
    reason: str | None = None
    source_document_id: uuid.UUID | None = None
    law_version_id: uuid.UUID | None = None
    court_decision_id: uuid.UUID | None = None


class IngestionPipeline:
    def __init__(
        self,
        session: AsyncSession,
        source: LegalDataSource,
        parser: SourceParser,
        normalizer: SourceNormalizer,
        validator: SourceValidator,
        indexer: LegalIndexer | None = None,
    ) -> None:
        self._session = session
        self._source = source
        self._parser = parser
        self._normalizer = normalizer
        self._validator = validator
        self._indexer = indexer

    async def discover(self, legal_source: LegalSource) -> list[str]:
        """All external ids this source currently exposes."""
        hits = await self._source.search(_empty_discovery_query())
        return [hit.external_id for hit in hits]

    async def ingest_document(self, legal_source: LegalSource, external_id: str) -> IngestResult:
        raw = await self._source.fetch(external_id)
        parsed = self._parser.parse(raw)
        parsed = self._normalizer.normalize(parsed)

        validation = self._validator.validate(parsed)
        if not validation.is_valid:
            raise IngestionValidationError(f"{external_id}: {'; '.join(validation.errors)}")

        normalized_text = _indexable_text(parsed)
        hash_value = content_hash(normalized_text)

        existing = await self._session.execute(
            select(SourceDocument).where(
                SourceDocument.source_id == legal_source.id, SourceDocument.content_hash == hash_value
            )
        )
        existing_row = existing.scalars().first()
        if existing_row is not None:
            return IngestResult(external_id=external_id, skipped=True, reason="duplicate content_hash", source_document_id=existing_row.id)

        source_document = SourceDocument(
            source_id=legal_source.id,
            external_id=external_id,
            source_url=raw.source_url,
            title=parsed.title,
            document_type=parsed.kind,
            jurisdiction=parsed.jurisdiction,
            publication_date=_iso(parsed.publication_date),
            effective_date=_iso(parsed.effective_date),
            content_hash=hash_value,
            retrieved_at=datetime.utcnow().isoformat(),
            raw_content=raw.content,
            normalized_content=normalized_text,
            source_metadata=raw.metadata,
        )
        self._session.add(source_document)
        await self._session.flush()

        if parsed.kind == "law_article":
            law_version = await self._persist_law_article(legal_source, source_document, parsed)
            if self._indexer is not None:
                await self._indexer.index_chunk(
                    "law_version",
                    law_version.id,
                    law_version.text,
                    {
                        "jurisdiction": parsed.jurisdiction,
                        "document_type": "law_article",
                        "law_id": str(law_version.law_id),
                        "law_version_id": str(law_version.id),
                        "law_short_name": parsed.law_short_name,
                        "article_number": law_version.article_number,
                        "effective_from": _iso(parsed.valid_from),
                        "effective_to": _iso(parsed.valid_to),
                        "source_id": str(legal_source.id),
                        "is_mock": legal_source.is_mock,
                    },
                )
            return IngestResult(
                external_id=external_id, skipped=False, source_document_id=source_document.id, law_version_id=law_version.id
            )

        court_decision = await self._persist_court_decision(legal_source, source_document, parsed)
        if self._indexer is not None:
            await self._indexer.index_chunk(
                "court_decision",
                court_decision.id,
                normalized_text,
                {
                    "jurisdiction": parsed.jurisdiction,
                    "document_type": "court_decision",
                    "court_decision_id": str(court_decision.id),
                    "case_number": parsed.case_number,
                    "court_name": parsed.court_name,
                    "source_id": str(legal_source.id),
                    "is_mock": legal_source.is_mock,
                },
            )
        return IngestResult(
            external_id=external_id, skipped=False, source_document_id=source_document.id, court_decision_id=court_decision.id
        )

    async def ingest_source(self, legal_source: LegalSource) -> list[IngestResult]:
        external_ids = await self.discover(legal_source)
        results = []
        for external_id in external_ids:
            results.append(await self.ingest_document(legal_source, external_id))
        return results

    async def sync_source(self, legal_source: LegalSource) -> list[IngestResult]:
        """Alias kept distinct from ingest_source (brief §18) — sync is meant to
        become incremental (`since=last_successful_sync_at`) once a real source
        supports it; today both walk the full discover() list.
        """
        return await self.ingest_source(legal_source)

    async def _persist_law_article(
        self, legal_source: LegalSource, source_document: SourceDocument, parsed: ParsedLegalContent
    ) -> LawVersion:
        TemporalLawResolver.validate_interval(parsed.valid_from, parsed.valid_to)  # type: ignore[arg-type]

        law = await self._get_or_create_law(legal_source, parsed)

        law_version = LawVersion(
            law_id=law.id,
            article_number=parsed.article_number,
            clause_number=parsed.clause_number,
            text=parsed.text,
            valid_from=parsed.valid_from,
            valid_to=parsed.valid_to,
            hierarchy_path=parsed.hierarchy_path,
            amending_act_title=parsed.amending_act_title,
            amending_act_source_url=parsed.amending_act_source_url,
            source_document_id=source_document.id,
        )
        self._session.add(law_version)
        await self._session.flush()
        return law_version

    async def _get_or_create_law(self, legal_source: LegalSource, parsed: ParsedLegalContent) -> Law:
        existing = await self._session.execute(select(Law).where(Law.short_name == parsed.law_short_name))
        law = existing.scalars().first()
        if law is not None:
            return law

        document = LegalDocument(
            title=parsed.law_full_name or parsed.law_short_name,
            document_type=LegalDocumentType.CODE,
            jurisdiction=parsed.jurisdiction,
            source_id=legal_source.id,
            publication_date=_iso(parsed.publication_date),
            effective_date=_iso(parsed.effective_date),
        )
        self._session.add(document)
        await self._session.flush()

        law = Law(
            document_id=document.id,
            short_name=parsed.law_short_name,
            full_name=parsed.law_full_name or parsed.law_short_name,
            code_type=parsed.code_type,
        )
        self._session.add(law)
        await self._session.flush()
        return law

    async def _persist_court_decision(
        self, legal_source: LegalSource, source_document: SourceDocument, parsed: ParsedLegalContent
    ) -> CourtDecision:
        court = await self._get_or_create_court(parsed)

        document = LegalDocument(
            title=parsed.title,
            document_type=LegalDocumentType.COURT_DECISION,
            jurisdiction=parsed.jurisdiction,
            source_id=legal_source.id,
            publication_date=_iso(parsed.publication_date),
            effective_date=_iso(parsed.effective_date),
            content=parsed.legal_reasoning or parsed.decision_summary,
        )
        self._session.add(document)
        await self._session.flush()

        decision = CourtDecision(
            document_id=document.id,
            court_id=court.id,
            case_number=parsed.case_number,
            decision_date=_iso(parsed.decision_date),
            parties=parsed.parties,
            claim_summary=parsed.claim_summary,
            decision_summary=parsed.decision_summary,
            legal_reasoning=parsed.legal_reasoning,
            outcome=parsed.outcome,
        )
        self._session.add(decision)
        await self._session.flush()
        return decision

    async def _get_or_create_court(self, parsed: ParsedLegalContent) -> Court:
        existing = await self._session.execute(select(Court).where(Court.name == parsed.court_name))
        court = existing.scalars().first()
        if court is not None:
            return court

        court = Court(name=parsed.court_name, level=CourtLevel(parsed.court_level), jurisdiction=parsed.jurisdiction)
        self._session.add(court)
        await self._session.flush()
        return court


def _empty_discovery_query() -> SourceQuery:
    return SourceQuery(text="", limit=1000)


def _indexable_text(parsed: ParsedLegalContent) -> str:
    """The text that gets hashed (dedup/change-detection) AND indexed for
    search. For a court decision this deliberately combines claim + decision
    + reasoning rather than reasoning alone — a real decision's searchable
    text is the whole document, not just one section of it.
    """
    if parsed.kind == "law_article":
        return parsed.text
    return " ".join(filter(None, [parsed.claim_summary, parsed.decision_summary, parsed.legal_reasoning]))


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None
