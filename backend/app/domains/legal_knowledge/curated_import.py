"""Human-curated legal document import — a manual staging ingestion path
(Phase 10 brief, curated-dataset task, rules 1-13).

This is deliberately NOT a `LegalDataSource` connector (rule 2). No
`fetch()`/`search()`/`sync()` exists here, nothing is registered in
`app.api.v1.knowledge._SOURCE_ADAPTERS`, and `LEGAL-SOURCE-MATRIX.md` is not
touched — vsrf.ru and every other `BLOCKED` web-UI source stay `BLOCKED` for
automated connectors. An operator who has personally read a public official
page hands this module the text directly; nothing here ever fetches anything.

Two supported `kind`s, matching what the schema can actually represent
honestly (rule 7):

- `law_article`  -> Law (get-or-create) + LawVersion, exactly like
  `IngestionPipeline._persist_law_article`.
- `interpretation` -> a bare `LegalDocument(document_type=INTERPRETATION)`.
  `ParsedContentKind` (app/domains/legal_knowledge/ingestion/protocols.py)
  only defines `"law_article" | "court_decision"` — there is no third path
  in `IngestionPipeline` for a Постановление Пленума/обзор, and forcing one
  through `_persist_court_decision` would require inventing a fake
  `case_number`/`court_id`/`parties`/`outcome` for a document that is none
  of those things (it isn't a case decision at all). `LegalDocumentType`
  already has a first-class `INTERPRETATION` value and `LegalDocument`'s own
  generic `content`/`content_hash`/`source_url`/dates/`doc_metadata` columns
  fit this content exactly, with no schema gap and no misrepresentation —
  see `retrieval_pipeline.py`'s Pass 2 comment, which already anticipated
  "when real official explanations are ingested".

Nothing here ever sets `verification_status`/`VERIFIED` — that is written
exclusively by `CitationValidator` (LEGAL-RAG.md §4), and only after its own
five real checks pass, exactly as for any other source (rules 3-4). This
module's only job is getting real, honestly-provenanced rows into the same
tables every other ingestion path writes to, so the *existing* validator has
something true to check.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_knowledge.ingestion.hashing import content_hash
from app.domains.legal_knowledge.ingestion.protocols import LegalIndexer
from app.domains.legal_knowledge.temporal_resolver import InvalidTemporalIntervalError, TemporalLawResolver
from app.models.legal_knowledge import Law, LawVersion, LegalDocument, LegalDocumentType, LegalSource, SourceType
from app.models.source_document import SourceDocument


class CuratedImportKind(str, enum.Enum):
    LAW_ARTICLE = "law_article"
    INTERPRETATION = "interpretation"


class CuratedImportValidationError(Exception):
    """Raised with every problem found (rule 8), not just the first, so an
    operator fixing a JSON file doesn't have to re-run it once per typo."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class CuratedImportConflictError(Exception):
    """Same logical document re-imported with different text (different
    content_hash) than what's already stored under the same identity — never
    silently overwritten (rule 13 hash-mismatch case)."""


@dataclass
class CuratedImportInput:
    kind: CuratedImportKind
    source_url: str
    confirmed_official_source: bool
    title: str
    text: str
    jurisdiction: str = "RU"
    publication_date: date | None = None
    effective_date: date | None = None
    imported_by: str | None = None

    # law_article only
    law_short_name: str | None = None
    law_full_name: str | None = None
    code_type: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    amending_act_title: str | None = None
    amending_act_source_url: str | None = None

    # interpretation only
    document_number: str | None = None
    document_subtype: str | None = None
    adoption_date: date | None = None


@dataclass
class CuratedImportPreview:
    kind: str
    content_hash: str
    source_name: str
    source_exists: bool
    would_create_source: bool
    is_official_to_set: bool
    would_skip_duplicate: bool
    duplicate_of_source_document_id: str | None = None
    would_conflict: bool = False
    conflicting_source_document_id: str | None = None
    law_short_name: str | None = None
    would_create_law: bool = False
    article_number: str | None = None
    document_number: str | None = None


@dataclass
class CuratedImportResult:
    dry_run: bool
    preview: CuratedImportPreview
    skipped: bool = False
    skip_reason: str | None = None
    source_document_id: uuid.UUID | None = None
    law_version_id: uuid.UUID | None = None
    legal_document_id: uuid.UUID | None = None
    embedding_indexed: bool = False


# ---------------------------------------------------------------------------
# Validation (rule 8) — pure, no DB access, so unit tests don't need Postgres.
# ---------------------------------------------------------------------------


def validate_input(raw: CuratedImportInput) -> None:
    errors: list[str] = []

    if not isinstance(raw.kind, CuratedImportKind):
        errors.append(f"Unknown document kind: {raw.kind!r}. Must be one of {[k.value for k in CuratedImportKind]}.")

    _require_https(raw.source_url, "source_url", errors)
    if raw.amending_act_source_url:
        _require_https(raw.amending_act_source_url, "amending_act_source_url", errors)

    if not raw.text or not raw.text.strip():
        errors.append("text must not be empty.")

    if not raw.title or not raw.title.strip():
        errors.append("title must not be empty.")

    if raw.confirmed_official_source is None:  # type: ignore[comparison-overlap]
        errors.append(
            "confirmed_official_source must be explicitly true or false — an operator must state whether the "
            "text was actually taken from the stated source_url, it is never assumed."
        )

    if raw.publication_date and raw.effective_date and raw.effective_date < raw.publication_date:
        errors.append(
            f"effective_date ({raw.effective_date}) is before publication_date ({raw.publication_date}) — "
            "inconsistent dates."
        )

    if raw.kind == CuratedImportKind.LAW_ARTICLE:
        _validate_law_article(raw, errors)
    elif raw.kind == CuratedImportKind.INTERPRETATION:
        _validate_interpretation(raw, errors)

    if errors:
        raise CuratedImportValidationError(errors)


def _require_https(url: str | None, field_name: str, errors: list[str]) -> None:
    if not url:
        errors.append(f"{field_name} is required.")
        return
    parsed = urlparse(url)
    if parsed.scheme != "https":
        errors.append(f"{field_name} must be HTTPS, got: {url!r}")


def _validate_law_article(raw: CuratedImportInput, errors: list[str]) -> None:
    if not raw.law_short_name:
        errors.append("law_article import requires law_short_name (e.g. 'ГК РФ').")
    if not raw.article_number:
        errors.append("law_article import requires article_number.")
    if raw.valid_from is None:
        errors.append("law_article import requires valid_from.")
    elif raw.valid_to is not None:
        try:
            TemporalLawResolver.validate_interval(raw.valid_from, raw.valid_to)
        except InvalidTemporalIntervalError as exc:
            errors.append(str(exc))


def _validate_interpretation(raw: CuratedImportInput, errors: list[str]) -> None:
    if not raw.document_number:
        errors.append("interpretation import requires document_number (e.g. '7').")
    if raw.adoption_date and raw.publication_date and raw.publication_date < raw.adoption_date:
        errors.append(
            f"publication_date ({raw.publication_date}) is before adoption_date ({raw.adoption_date}) — "
            "inconsistent dates."
        )
    if raw.adoption_date and raw.effective_date and raw.effective_date < raw.adoption_date:
        errors.append(
            f"effective_date ({raw.effective_date}) is before adoption_date ({raw.adoption_date}) — "
            "inconsistent dates."
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_SOURCE_NAMES = {
    (CuratedImportKind.LAW_ARTICLE, True): "Manual Curated Import — Confirmed Official (Legislation)",
    (CuratedImportKind.LAW_ARTICLE, False): "Manual Curated Import — Unconfirmed (Legislation)",
    (CuratedImportKind.INTERPRETATION, True): "Manual Curated Import — Confirmed Official (Court/Interpretation)",
    (CuratedImportKind.INTERPRETATION, False): "Manual Curated Import — Unconfirmed (Court/Interpretation)",
}
_SOURCE_TYPE_BY_KIND = {
    CuratedImportKind.LAW_ARTICLE: SourceType.OFFICIAL_GOV,
    CuratedImportKind.INTERPRETATION: SourceType.COURT,
}
CURATED_IMPORT_PROVIDER = "manual-curated-import"


class CuratedImportService:
    """One operator-facing entrypoint: `preview()` (dry-run, no writes) and
    `import_document()` (real write). Both run the exact same validation and
    lookup logic — `preview()` just stops before any `session.add()`.
    """

    def __init__(self, session: AsyncSession, indexer: LegalIndexer | None = None) -> None:
        self._session = session
        self._indexer = indexer

    async def preview(self, raw: CuratedImportInput) -> CuratedImportResult:
        validate_input(raw)
        preview = await self._build_preview(raw)
        return CuratedImportResult(dry_run=True, preview=preview)

    async def import_document(self, raw: CuratedImportInput) -> CuratedImportResult:
        validate_input(raw)
        preview = await self._build_preview(raw)

        if preview.would_conflict:
            raise CuratedImportConflictError(
                f"A document with the same identity already exists (source_document_id="
                f"{preview.conflicting_source_document_id}) but with DIFFERENT content — refusing to "
                "silently overwrite. Delete/supersede the existing record explicitly if the text genuinely "
                "changed, or fix the input if this was a mistake."
            )

        legal_source = await self._get_or_create_source(raw)

        if preview.would_skip_duplicate:
            return CuratedImportResult(
                dry_run=False,
                preview=preview,
                skipped=True,
                skip_reason="duplicate content_hash for this source/identity — already imported, no-op.",
                source_document_id=uuid.UUID(preview.duplicate_of_source_document_id)
                if preview.duplicate_of_source_document_id
                else None,
            )

        normalized_text = raw.text.strip()
        hash_value = content_hash(normalized_text)
        imported_at = datetime.now(timezone.utc).isoformat()
        external_id = _external_id(raw)

        source_document = SourceDocument(
            source_id=legal_source.id,
            external_id=external_id,
            source_url=raw.source_url,
            title=raw.title,
            document_type=raw.kind.value,
            jurisdiction=raw.jurisdiction,
            publication_date=_iso(raw.publication_date),
            effective_date=_iso(raw.effective_date),
            content_hash=hash_value,
            retrieved_at=imported_at,
            raw_content=raw.text,
            normalized_content=normalized_text,
            source_metadata={
                "curated_import": True,
                "imported_by": raw.imported_by,
                "imported_at": imported_at,
                "confirmed_official_source": raw.confirmed_official_source,
                "document_number": raw.document_number,
                "document_subtype": raw.document_subtype,
            },
        )
        self._session.add(source_document)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise CuratedImportConflictError(f"Database rejected this import: {exc}") from exc

        if raw.kind == CuratedImportKind.LAW_ARTICLE:
            law_version = await self._persist_law_article(legal_source, source_document, raw)
            if self._indexer is not None:
                await self._indexer.index_chunk(
                    "law_version",
                    law_version.id,
                    law_version.text,
                    {
                        "jurisdiction": raw.jurisdiction,
                        "document_type": "law_article",
                        "law_id": str(law_version.law_id),
                        "law_version_id": str(law_version.id),
                        "law_short_name": raw.law_short_name,
                        "article_number": law_version.article_number,
                        "effective_from": _iso(raw.valid_from),
                        "effective_to": _iso(raw.valid_to),
                        "source_id": str(legal_source.id),
                        "is_mock": False,
                    },
                )
            return CuratedImportResult(
                dry_run=False,
                preview=preview,
                source_document_id=source_document.id,
                law_version_id=law_version.id,
                embedding_indexed=self._indexer is not None,
            )

        legal_document = await self._persist_interpretation(legal_source, source_document, raw)
        if self._indexer is not None:
            await self._indexer.index_chunk(
                "legal_document",
                legal_document.id,
                normalized_text,
                {
                    "jurisdiction": raw.jurisdiction,
                    "document_type": "interpretation",
                    "source_id": str(legal_source.id),
                    "is_mock": False,
                },
            )
        return CuratedImportResult(
            dry_run=False,
            preview=preview,
            source_document_id=source_document.id,
            legal_document_id=legal_document.id,
            embedding_indexed=self._indexer is not None,
        )

    async def _build_preview(self, raw: CuratedImportInput) -> CuratedImportPreview:
        normalized_text = raw.text.strip()
        hash_value = content_hash(normalized_text)
        source_name = _SOURCE_NAMES[(raw.kind, raw.confirmed_official_source)]

        existing_source = await self._session.execute(select(LegalSource).where(LegalSource.name == source_name))
        legal_source = existing_source.scalars().first()

        would_skip_duplicate = False
        duplicate_id: str | None = None
        would_conflict = False
        conflict_id: str | None = None

        if legal_source is not None:
            external_id = _external_id(raw)
            same_identity = await self._session.execute(
                select(SourceDocument).where(
                    SourceDocument.source_id == legal_source.id, SourceDocument.external_id == external_id
                )
            )
            existing_row = same_identity.scalars().first()
            if existing_row is not None:
                if existing_row.content_hash == hash_value:
                    would_skip_duplicate = True
                    duplicate_id = str(existing_row.id)
                else:
                    would_conflict = True
                    conflict_id = str(existing_row.id)

        would_create_law = False
        if raw.kind == CuratedImportKind.LAW_ARTICLE and raw.law_short_name:
            existing_law = await self._session.execute(select(Law).where(Law.short_name == raw.law_short_name))
            would_create_law = existing_law.scalars().first() is None

        return CuratedImportPreview(
            kind=raw.kind.value,
            content_hash=hash_value,
            source_name=source_name,
            source_exists=legal_source is not None,
            would_create_source=legal_source is None,
            is_official_to_set=raw.confirmed_official_source,
            would_skip_duplicate=would_skip_duplicate,
            duplicate_of_source_document_id=duplicate_id,
            would_conflict=would_conflict,
            conflicting_source_document_id=conflict_id,
            law_short_name=raw.law_short_name,
            would_create_law=would_create_law,
            article_number=raw.article_number,
            document_number=raw.document_number,
        )

    async def _get_or_create_source(self, raw: CuratedImportInput) -> LegalSource:
        source_name = _SOURCE_NAMES[(raw.kind, raw.confirmed_official_source)]
        existing = await self._session.execute(select(LegalSource).where(LegalSource.name == source_name))
        source = existing.scalars().first()
        if source is not None:
            return source

        source = LegalSource(
            name=source_name,
            type=_SOURCE_TYPE_BY_KIND[raw.kind],
            provider=CURATED_IMPORT_PROVIDER,
            jurisdiction=raw.jurisdiction,
            base_url=None,
            status="active",
            is_official=raw.confirmed_official_source,
            is_mock=False,
            is_licensed=False,
        )
        self._session.add(source)
        await self._session.flush()
        return source

    async def _persist_law_article(
        self, legal_source: LegalSource, source_document: SourceDocument, raw: CuratedImportInput
    ) -> LawVersion:
        law = await self._get_or_create_law(legal_source, raw)
        law_version = LawVersion(
            law_id=law.id,
            article_number=raw.article_number,
            clause_number=raw.clause_number,
            text=raw.text.strip(),
            valid_from=raw.valid_from,
            valid_to=raw.valid_to,
            hierarchy_path=[raw.law_short_name, f"Статья {raw.article_number}"] if raw.article_number else [],
            amending_act_title=raw.amending_act_title,
            amending_act_source_url=raw.amending_act_source_url,
            source_document_id=source_document.id,
        )
        self._session.add(law_version)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise CuratedImportConflictError(
                f"Overlapping validity period for {raw.law_short_name} ст.{raw.article_number} "
                f"({raw.valid_from}..{raw.valid_to}) — a version already covers this range: {exc}"
            ) from exc
        return law_version

    async def _get_or_create_law(self, legal_source: LegalSource, raw: CuratedImportInput) -> Law:
        existing = await self._session.execute(select(Law).where(Law.short_name == raw.law_short_name))
        law = existing.scalars().first()
        if law is not None:
            return law

        document = LegalDocument(
            title=raw.law_full_name or raw.law_short_name,
            document_type=LegalDocumentType.CODE,
            jurisdiction=raw.jurisdiction,
            source_id=legal_source.id,
            source_url=raw.source_url,
            publication_date=_iso(raw.publication_date),
            effective_date=_iso(raw.effective_date),
            doc_metadata={"curated_import": True, "imported_by": raw.imported_by},
        )
        self._session.add(document)
        await self._session.flush()

        law = Law(
            document_id=document.id,
            short_name=raw.law_short_name,
            full_name=raw.law_full_name or raw.law_short_name,
            code_type=raw.code_type,
        )
        self._session.add(law)
        await self._session.flush()
        return law

    async def _persist_interpretation(
        self, legal_source: LegalSource, source_document: SourceDocument, raw: CuratedImportInput
    ) -> LegalDocument:
        document = LegalDocument(
            title=raw.title,
            document_type=LegalDocumentType.INTERPRETATION,
            jurisdiction=raw.jurisdiction,
            source_id=legal_source.id,
            source_url=raw.source_url,
            publication_date=_iso(raw.publication_date),
            effective_date=_iso(raw.effective_date),
            content=raw.text.strip(),
            content_hash=source_document.content_hash,
            doc_metadata={
                "curated_import": True,
                "imported_by": raw.imported_by,
                "document_number": raw.document_number,
                "document_subtype": raw.document_subtype,
                "adoption_date": _iso(raw.adoption_date),
                "confirmed_official_source": raw.confirmed_official_source,
            },
        )
        self._session.add(document)
        await self._session.flush()
        return document


def _external_id(raw: CuratedImportInput) -> str:
    """Deterministic per-logical-document identity (not per content) — the
    SAME logical article/resolution imported twice gets the same external_id
    every time, so a second import is recognized as either an idempotent
    duplicate (same hash) or a genuine conflict (different hash), never a
    silently-created second row (rule 13).
    """
    if raw.kind == CuratedImportKind.LAW_ARTICLE:
        return "curated:law:{}:{}:{}:{}".format(
            raw.law_short_name, raw.article_number, raw.clause_number or "-", raw.valid_from.isoformat() if raw.valid_from else "-"
        )
    return "curated:interpretation:{}:{}".format(
        raw.document_number, raw.adoption_date.isoformat() if raw.adoption_date else "-"
    )


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None
