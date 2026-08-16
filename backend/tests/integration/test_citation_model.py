"""Citation model + CitationValidator — LEGAL-RAG.md §4, the anti-hallucination gate."""
from __future__ import annotations

from datetime import date

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.legal_knowledge import Law, LawVersion, LegalDocument, LegalDocumentType, LegalSource, SourceType
from app.models.source_document import SourceDocument
from app.rag.validation.citation_validator import CitationDraft, CitationStatus, CitationValidator
from app.sources.mock.mock_source import MockLegalDataSource


@pytest.mark.asyncio
async def test_citation_validator_verifies_matching_quote(db_session):
    document = LegalDocument(title="ГК РФ", document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()
    law = Law(document_id=document.id, short_name="ГК РФ", full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()
    version = LawVersion(
        law_id=law.id, article_number="309", text="Обязательства должны исполняться надлежащим образом.",
        valid_from=date(2020, 1, 1), valid_to=None,
    )
    db_session.add(version)
    await db_session.flush()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="ГК РФ", article_number="309", quoted_fragment="исполняться надлежащим образом")
    )

    assert check.status == "verified"


@pytest.mark.asyncio
async def test_citation_validator_marks_unknown_article_unverified(db_session):
    validator = CitationValidator(db_session)
    check = await validator.validate(CitationDraft(law_short_name="ГК РФ", article_number="99999", quoted_fragment="anything"))
    assert check.status == "unverified"


@pytest.mark.asyncio
async def test_citation_validator_marks_mismatched_quote_broken(db_session):
    document = LegalDocument(title="ГК РФ", document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()
    law = Law(document_id=document.id, short_name="ГК РФ", full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()
    version = LawVersion(law_id=law.id, article_number="310", text="Real text here.", valid_from=date(2020, 1, 1), valid_to=None)
    db_session.add(version)
    await db_session.flush()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="ГК РФ", article_number="310", quoted_fragment="This quote does not exist in the text")
    )
    assert check.status == "broken"


@pytest.mark.asyncio
async def test_citation_validator_marks_out_of_force_date_temporally_invalid(db_session):
    document = LegalDocument(title="ГК РФ", document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()
    law = Law(document_id=document.id, short_name="ГК РФ", full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()
    version = LawVersion(
        law_id=law.id, article_number="309", text="Old text.", valid_from=date(2020, 1, 1), valid_to=date(2022, 1, 1)
    )
    db_session.add(version)
    await db_session.flush()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="ГК РФ", article_number="309", quoted_fragment=None, event_date=date(2023, 1, 1))
    )

    assert check.status == CitationStatus.TEMPORALLY_INVALID


@pytest.mark.asyncio
async def test_citation_validator_marks_mock_source_citations_as_mock(db_session):
    source = LegalSource(name="Mock", type=SourceType.USER_UPLOAD, is_mock=True)
    db_session.add(source)
    await db_session.flush()
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())
    result = await pipeline.ingest_document(source, "mock-gk-314")
    await db_session.commit()
    assert result.law_version_id is not None

    validator = CitationValidator(db_session)
    check = await validator.validate(CitationDraft(law_short_name="ГК РФ", article_number="314", quoted_fragment=None))

    assert check.status == CitationStatus.MOCK


@pytest.mark.asyncio
async def test_citation_validator_marks_hash_mismatch_broken(db_session):
    source = LegalSource(name="Mock", type=SourceType.USER_UPLOAD, is_mock=True)
    db_session.add(source)
    await db_session.flush()
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())
    result = await pipeline.ingest_document(source, "mock-gk-314")
    await db_session.commit()

    # Simulate provenance corruption: the SourceDocument's recorded hash no
    # longer matches its own normalized_content.
    law_version = await db_session.get(LawVersion, result.law_version_id)
    source_document = await db_session.get(SourceDocument, law_version.source_document_id)
    source_document.content_hash = "0" * 64
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(CitationDraft(law_short_name="ГК РФ", article_number="314", quoted_fragment=None))

    assert check.status == CitationStatus.BROKEN
    assert "provenance" in check.reason.lower()


@pytest.mark.asyncio
async def test_citation_validator_skips_hash_check_for_hand_seeded_versions(db_session):
    """A LawVersion created directly (not through ingestion) has no
    source_document_id — that's a missing-provenance situation, not a hash
    mismatch, and must not be misreported as BROKEN.
    """
    document = LegalDocument(title="ГК РФ", document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()
    law = Law(document_id=document.id, short_name="ГК РФ", full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()
    version = LawVersion(law_id=law.id, article_number="1", text="text", valid_from=date(2020, 1, 1), valid_to=None)
    db_session.add(version)
    await db_session.flush()

    validator = CitationValidator(db_session)
    check = await validator.validate(CitationDraft(law_short_name="ГК РФ", article_number="1", quoted_fragment=None))

    assert check.status == CitationStatus.VERIFIED
