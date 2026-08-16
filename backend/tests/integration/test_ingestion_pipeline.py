"""IngestionPipeline against the deterministic mock dataset — LEGAL-SOURCES.md
§2/§11-13, brief §17-18. Exercises discover -> fetch -> parse -> normalize ->
validate -> hash -> deduplicate -> persist end to end against a real DB.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.case_law import Court, CourtDecision
from app.models.legal_knowledge import Law, LawVersion, LegalSource, SourceType
from app.models.source_document import SourceDocument
from app.sources.mock.dataset import MOCK_COURT_DECISIONS, MOCK_LAW_ARTICLES
from app.sources.mock.mock_source import MockLegalDataSource


async def _make_mock_legal_source(db_session) -> LegalSource:
    source = LegalSource(name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, is_mock=True, is_official=False)
    db_session.add(source)
    await db_session.flush()
    return source


@pytest.mark.asyncio
async def test_discover_returns_every_mock_external_id(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    discovered = await pipeline.discover(source)

    assert len(discovered) == len(MOCK_LAW_ARTICLES) + len(MOCK_COURT_DECISIONS)
    assert "mock-gk-309-v1" in discovered
    assert "mock-case-a40-000001-2025" in discovered


@pytest.mark.asyncio
async def test_ingest_law_article_persists_law_and_law_version(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    result = await pipeline.ingest_document(source, "mock-gk-309-v1")
    await db_session.commit()

    assert result.skipped is False
    assert result.law_version_id is not None

    law_version = await db_session.get(LawVersion, result.law_version_id)
    assert law_version.article_number == "309"
    assert law_version.valid_to.isoformat() == "2025-01-01"

    law = await db_session.get(Law, law_version.law_id)
    assert law.short_name == "ГК РФ"


@pytest.mark.asyncio
async def test_ingest_second_version_of_same_article_shares_one_law_row(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    r1 = await pipeline.ingest_document(source, "mock-gk-309-v1")
    r2 = await pipeline.ingest_document(source, "mock-gk-309-v2")
    await db_session.commit()

    v1 = await db_session.get(LawVersion, r1.law_version_id)
    v2 = await db_session.get(LawVersion, r2.law_version_id)
    assert v1.law_id == v2.law_id

    result = await db_session.execute(select(Law).where(Law.short_name == "ГК РФ"))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_ingest_same_document_twice_is_deduplicated(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    first = await pipeline.ingest_document(source, "mock-gk-314")
    await db_session.commit()
    second = await pipeline.ingest_document(source, "mock-gk-314")
    await db_session.commit()

    assert first.skipped is False
    assert second.skipped is True
    assert second.reason == "duplicate content_hash"

    result = await db_session.execute(select(SourceDocument).where(SourceDocument.source_id == source.id))
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_ingest_court_decision_persists_court_and_decision(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    result = await pipeline.ingest_document(source, "mock-case-a40-000001-2025")
    await db_session.commit()

    assert result.court_decision_id is not None
    decision = await db_session.get(CourtDecision, result.court_decision_id)
    assert decision.case_number == "А40-000001/2025"
    assert decision.outcome == "partial"

    court = await db_session.get(Court, decision.court_id)
    assert "Арбитражный суд" in court.name


@pytest.mark.asyncio
async def test_two_decisions_from_same_court_share_one_court_row(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    r1 = await pipeline.ingest_document(source, "mock-case-a40-000001-2025")
    r2 = await pipeline.ingest_document(source, "mock-case-a40-000002-2025")
    await db_session.commit()

    d1 = await db_session.get(CourtDecision, r1.court_decision_id)
    d2 = await db_session.get(CourtDecision, r2.court_decision_id)
    assert d1.court_id == d2.court_id


@pytest.mark.asyncio
async def test_ingest_source_ingests_entire_mock_dataset(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    results = await pipeline.ingest_source(source)
    await db_session.commit()

    assert len(results) == len(MOCK_LAW_ARTICLES) + len(MOCK_COURT_DECISIONS)
    assert all(not r.skipped for r in results)

    law_versions = await db_session.execute(select(LawVersion))
    assert len(law_versions.scalars().all()) == len(MOCK_LAW_ARTICLES)

    decisions = await db_session.execute(select(CourtDecision))
    assert len(decisions.scalars().all()) == len(MOCK_COURT_DECISIONS)


@pytest.mark.asyncio
async def test_validator_rejects_invalid_interval():
    from app.domains.legal_knowledge.ingestion.protocols import ParsedLegalContent

    validator = MockSourceValidator()
    parsed = ParsedLegalContent(
        kind="law_article", title="broken", law_short_name="X", article_number="1",
        text="text", valid_from=__import__("datetime").date(2025, 1, 1), valid_to=__import__("datetime").date(2024, 1, 1),
    )
    result = validator.validate(parsed)
    assert result.is_valid is False
    assert any("valid_to" in e for e in result.errors)


@pytest.mark.asyncio
async def test_ingest_document_raises_on_unknown_external_id(db_session):
    source = await _make_mock_legal_source(db_session)
    pipeline = IngestionPipeline(db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator())

    with pytest.raises(KeyError):
        await pipeline.ingest_document(source, "does-not-exist")
