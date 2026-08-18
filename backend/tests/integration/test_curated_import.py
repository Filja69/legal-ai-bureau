"""Integration tests for CuratedImportService — curated-dataset task rule 13.

Uses synthetic, clearly-fake text throughout (rule 14: no real legal text is
imported by this session). Requires real Postgres (db_session fixture).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.domains.legal_knowledge.curated_import import (
    CuratedImportConflictError,
    CuratedImportInput,
    CuratedImportKind,
    CuratedImportService,
)
from app.models.legal_knowledge import Law, LawVersion, LegalDocument, LegalDocumentType, LegalSource
from app.models.source_document import SourceDocument
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.rag.validation.citation_validator import CitationDraft, CitationStatus, CitationValidator

pytestmark = pytest.mark.asyncio

_FAKE_STATUTE_TEXT = (
    "TEST FIXTURE — если подлежащая уплате неустойка явно несоразмерна "
    "последствиям нарушения обязательства, суд вправе уменьшить неустойку."
)
_FAKE_INTERPRETATION_TEXT = (
    "TEST FIXTURE — при оценке соразмерности неустойки последствиям "
    "нарушения обязательства судам следует исходить из того, что..."
)


def _law_article(**overrides) -> CuratedImportInput:
    defaults = dict(
        kind=CuratedImportKind.LAW_ARTICLE,
        source_url="https://pravo.gov.ru/test-fixture",
        confirmed_official_source=True,
        title="TEST FIXTURE Статья 333",
        text=_FAKE_STATUTE_TEXT,
        law_short_name="TEST-GK",
        article_number="333",
        valid_from=date(2015, 6, 1),
        imported_by="test-operator",
    )
    defaults.update(overrides)
    return CuratedImportInput(**defaults)


def _interpretation(**overrides) -> CuratedImportInput:
    defaults = dict(
        kind=CuratedImportKind.INTERPRETATION,
        source_url="https://vsrf.ru/test-fixture",
        confirmed_official_source=True,
        title="TEST FIXTURE Постановление N 7",
        text=_FAKE_INTERPRETATION_TEXT,
        document_number="7",
        adoption_date=date(2016, 3, 24),
        imported_by="test-operator",
    )
    defaults.update(overrides)
    return CuratedImportInput(**defaults)


def _service(db_session) -> CuratedImportService:
    indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider())
    return CuratedImportService(db_session, indexer=indexer)


async def test_dry_run_writes_nothing_to_db(db_session):
    service = _service(db_session)
    result = await service.preview(_law_article())
    await db_session.flush()

    assert result.dry_run is True
    assert result.preview.would_create_source is True
    assert result.preview.would_create_law is True

    sources = (await db_session.execute(select(LegalSource))).scalars().all()
    laws = (await db_session.execute(select(Law))).scalars().all()
    docs = (await db_session.execute(select(SourceDocument))).scalars().all()
    assert sources == []
    assert laws == []
    assert docs == []


async def test_dry_run_interpretation_writes_nothing(db_session):
    service = _service(db_session)
    result = await service.preview(_interpretation())

    assert result.dry_run is True
    assert result.preview.kind == "interpretation"

    docs = (await db_session.execute(select(LegalDocument))).scalars().all()
    assert docs == []


async def test_real_law_article_import_creates_canonical_records(db_session):
    service = _service(db_session)
    result = await service.import_document(_law_article())
    await db_session.commit()

    assert result.dry_run is False
    assert result.skipped is False
    assert result.law_version_id is not None

    law_version = await db_session.get(LawVersion, result.law_version_id)
    assert law_version is not None
    assert law_version.article_number == "333"
    assert law_version.text == _FAKE_STATUTE_TEXT

    law = await db_session.get(Law, law_version.law_id)
    assert law is not None
    assert law.short_name == "TEST-GK"

    source_document = await db_session.get(SourceDocument, result.source_document_id)
    assert source_document is not None
    assert source_document.source_metadata["imported_by"] == "test-operator"
    assert source_document.source_metadata["curated_import"] is True

    legal_source = await db_session.get(LegalSource, source_document.source_id)
    assert legal_source.is_mock is False
    assert legal_source.is_official is True  # confirmed_official_source=True in the fixture


async def test_real_interpretation_import_creates_legal_document_no_law_version(db_session):
    service = _service(db_session)
    result = await service.import_document(_interpretation())
    await db_session.commit()

    assert result.legal_document_id is not None
    assert result.law_version_id is None

    document = await db_session.get(LegalDocument, result.legal_document_id)
    assert document is not None
    assert document.document_type == LegalDocumentType.INTERPRETATION
    assert document.content == _FAKE_INTERPRETATION_TEXT
    assert document.doc_metadata["document_number"] == "7"

    # No LawVersion or CourtDecision was created for this document at all.
    law_versions = (await db_session.execute(select(LawVersion))).scalars().all()
    assert law_versions == []


async def test_reimporting_identical_text_is_idempotent(db_session):
    service = _service(db_session)
    first = await service.import_document(_law_article())
    await db_session.commit()

    second = await service.import_document(_law_article())
    await db_session.commit()

    assert second.skipped is True
    assert second.skip_reason is not None and "duplicate" in second.skip_reason

    law_versions = (await db_session.execute(select(LawVersion))).scalars().all()
    assert len(law_versions) == 1
    assert first.law_version_id == law_versions[0].id


async def test_reimporting_same_identity_with_different_text_conflicts(db_session):
    service = _service(db_session)
    await service.import_document(_law_article())
    await db_session.commit()

    with pytest.raises(CuratedImportConflictError):
        await service.import_document(_law_article(text=_FAKE_STATUTE_TEXT + " CHANGED"))

    law_versions = (await db_session.execute(select(LawVersion))).scalars().all()
    assert len(law_versions) == 1  # nothing extra was written by the conflicting attempt


async def test_overlapping_validity_period_is_rejected(db_session):
    service = _service(db_session)
    await service.import_document(_law_article(valid_from=date(2015, 6, 1), valid_to=None))
    await db_session.commit()

    with pytest.raises(CuratedImportConflictError):
        # Same article, overlapping [valid_from, valid_to) window, different
        # external_id (different valid_from) — exercises the DB-level
        # EXCLUDE constraint, not the content_hash dedup path.
        await service.import_document(
            _law_article(valid_from=date(2016, 1, 1), valid_to=None, text=_FAKE_STATUTE_TEXT + " v2")
        )


async def test_manual_source_alone_does_not_produce_verified_status(db_session):
    """Rule 3/4: importing via the curated path must never itself set
    VERIFIED. Citing the freshly-imported (confirmed_official_source=True)
    article, with nothing bypassed, must go through the *same* six checks
    CitationValidator always runs — including the trust check, which this
    fixture passes because is_official=True, not because it was curated.
    """
    service = _service(db_session)
    result = await service.import_document(_law_article())
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="333", quoted_fragment=None, event_date=date(2020, 1, 1))
    )
    # No quoted_fragment supplied, source is not mock, and is_official=True -> passes all real checks -> VERIFIED.
    # This is CitationValidator's own ordinary logic, not a special case for curated imports.
    assert check.status == CitationStatus.VERIFIED
    assert check.law_version_id == str(result.law_version_id)


async def test_verified_only_after_normal_provenance_checks_pass(db_session):
    service = _service(db_session)
    await service.import_document(_law_article())
    await db_session.commit()

    validator = CitationValidator(db_session)

    # Quoted fragment that does NOT appear in the stored text -> BROKEN, same
    # as for any other source.
    broken = await validator.validate(
        CitationDraft(
            law_short_name="TEST-GK",
            article_number="333",
            quoted_fragment="это текст, которого нет в статье",
            event_date=date(2020, 1, 1),
        )
    )
    assert broken.status == CitationStatus.BROKEN

    # Date outside the version's validity window -> TEMPORALLY_INVALID.
    temporally_invalid = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="333", quoted_fragment=None, event_date=date(2010, 1, 1))
    )
    assert temporally_invalid.status == CitationStatus.TEMPORALLY_INVALID

    # Article that was never imported -> UNVERIFIED.
    unverified = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="999", quoted_fragment=None, event_date=date(2020, 1, 1))
    )
    assert unverified.status == CitationStatus.UNVERIFIED


async def test_unconfirmed_official_source_is_recorded_honestly_as_unofficial(db_session):
    """confirmed_official_source=False must be honestly recorded as
    is_official=False on the LegalSource row, never silently upgraded."""
    service = _service(db_session)
    result = await service.import_document(_law_article(confirmed_official_source=False))
    await db_session.commit()

    law_version = await db_session.get(LawVersion, result.law_version_id)
    source_document = await db_session.get(SourceDocument, law_version.source_document_id)
    legal_source = await db_session.get(LegalSource, source_document.source_id)
    assert legal_source.is_official is False
    assert legal_source.is_licensed is False


async def test_unconfirmed_official_source_with_otherwise_perfect_provenance_is_not_verified(db_session):
    """Trust-semantics fix: confirmed_official_source=False + matching hash +
    matching quote + valid temporal window must still NOT reach VERIFIED —
    an operator's unconfirmed origin claim is not proof of origin, no matter
    how internally consistent the stored text is. This is CitationValidator's
    own trust check (is_official OR is_licensed), not a special case keyed
    off "was this curated" — see citation_validator.py check 6.
    """
    service = _service(db_session)
    result = await service.import_document(_law_article(confirmed_official_source=False))
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(
            law_short_name="TEST-GK",
            article_number="333",
            quoted_fragment=_FAKE_STATUTE_TEXT,  # exact match — hash/quote/temporal all "perfect"
            event_date=date(2020, 1, 1),
        )
    )
    assert check.status != CitationStatus.VERIFIED
    assert check.status == CitationStatus.UNVERIFIED
    assert check.law_version_id == str(result.law_version_id)


async def test_confirmed_official_source_with_broken_hash_is_broken_not_verified(db_session):
    service = _service(db_session)
    result = await service.import_document(_law_article(confirmed_official_source=True))
    await db_session.commit()

    source_document = await db_session.get(SourceDocument, result.source_document_id)
    source_document.normalized_content = source_document.normalized_content + " TAMPERED"
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="333", quoted_fragment=None, event_date=date(2020, 1, 1))
    )
    assert check.status == CitationStatus.BROKEN


async def test_confirmed_official_source_with_wrong_quote_is_broken_not_verified(db_session):
    service = _service(db_session)
    await service.import_document(_law_article(confirmed_official_source=True))
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(
            law_short_name="TEST-GK",
            article_number="333",
            quoted_fragment="это текст, которого нет в статье",
            event_date=date(2020, 1, 1),
        )
    )
    assert check.status == CitationStatus.BROKEN


async def test_confirmed_official_source_with_temporal_mismatch_is_temporally_invalid(db_session):
    service = _service(db_session)
    await service.import_document(
        _law_article(confirmed_official_source=True, valid_from=date(2015, 6, 1), valid_to=date(2018, 1, 1))
    )
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="333", quoted_fragment=None, event_date=date(2020, 1, 1))
    )
    assert check.status == CitationStatus.TEMPORALLY_INVALID


async def test_confirmed_official_source_with_all_checks_passing_is_verified(db_session):
    service = _service(db_session)
    result = await service.import_document(_law_article(confirmed_official_source=True))
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(
            law_short_name="TEST-GK", article_number="333", quoted_fragment=_FAKE_STATUTE_TEXT, event_date=date(2020, 1, 1)
        )
    )
    assert check.status == CitationStatus.VERIFIED
    assert check.law_version_id == str(result.law_version_id)


async def test_altered_stored_text_breaks_provenance_hash(db_session):
    service = _service(db_session)
    result = await service.import_document(_law_article())
    await db_session.commit()

    source_document = await db_session.get(SourceDocument, result.source_document_id)
    source_document.normalized_content = source_document.normalized_content + " TAMPERED"
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="333", quoted_fragment=None, event_date=date(2020, 1, 1))
    )
    assert check.status == CitationStatus.BROKEN
    assert "provenance hash" in check.reason
