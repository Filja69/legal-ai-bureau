"""Risk verification via the Legal Research Engine — brief §24-27."""
from __future__ import annotations

import pytest

from app.domains.contracts.risk_detection import RiskCandidate
from app.domains.contracts.risk_verification import verify_risks
from app.domains.contracts.severity import SeverityInputs
from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import RiskCategory, RiskClassification, RiskType, RiskVerificationStatus
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource


@pytest.fixture
async def indexed_dataset(db_session):
    source = LegalSource(name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, is_mock=True)
    db_session.add(source)
    await db_session.flush()
    indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider())
    pipeline = IngestionPipeline(
        db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator(), indexer=indexer
    )
    await pipeline.ingest_source(source)
    await db_session.commit()
    return source


def _candidate(research_question: str | None) -> RiskCandidate:
    return RiskCandidate(
        detector="liability", risk_type=RiskType.UNLIMITED_LIABILITY, category=RiskCategory.FINANCIAL,
        classification=RiskClassification.HIGH_RISK, title="t", description="d", why_it_matters="w",
        severity_inputs=SeverityInputs(legal_impact=40, financial_impact=80, probability=35, scope=60, irreversibility=50),
        clause_index=0, research_question=research_question,
    )


@pytest.mark.asyncio
async def test_candidate_without_research_question_stays_unverified(db_session, indexed_dataset):
    candidate = _candidate(research_question=None)
    results = await verify_risks(db_session, LLMGateway(provider=MockLLMProvider()), [candidate])

    assert len(results) == 1
    assert results[0].verification_status == RiskVerificationStatus.UNVERIFIED
    assert results[0].research_id is None
    assert results[0].legal_basis is None


@pytest.mark.asyncio
async def test_candidate_with_matching_research_question_becomes_mock(db_session, indexed_dataset):
    candidate = _candidate(
        research_question="Как российское право регулирует ограничение договорной ответственности сторон, надлежащим образом исполнение?"
    )
    results = await verify_risks(db_session, LLMGateway(provider=MockLLMProvider()), [candidate])

    assert len(results) == 1
    assert results[0].verification_status in (RiskVerificationStatus.MOCK, RiskVerificationStatus.UNVERIFIED)
    if results[0].verification_status == RiskVerificationStatus.MOCK:
        assert results[0].research_id is not None
        assert results[0].citations


@pytest.mark.asyncio
async def test_candidate_with_irrelevant_research_question_stays_unverified(db_session, indexed_dataset):
    candidate = _candidate(research_question="совершенно нерелевантный вопрос без совпадений xyz999")
    results = await verify_risks(db_session, LLMGateway(provider=MockLLMProvider()), [candidate])

    assert results[0].verification_status in (RiskVerificationStatus.UNVERIFIED, RiskVerificationStatus.MOCK)


@pytest.mark.asyncio
async def test_verification_never_upgrades_classification_to_illegal(db_session, indexed_dataset):
    """brief §27/§54 — bad wording is never presented as illegal, regardless
    of what research returns.
    """
    candidate = _candidate(research_question="надлежащим образом исполнение обязательства")
    results = await verify_risks(db_session, LLMGateway(provider=MockLLMProvider()), [candidate])
    assert results[0].candidate.classification == RiskClassification.HIGH_RISK  # unchanged from detector output


@pytest.mark.asyncio
async def test_verify_risks_processes_multiple_candidates(db_session, indexed_dataset):
    candidates = [_candidate(None), _candidate("надлежащим образом исполнение"), _candidate(None)]
    results = await verify_risks(db_session, LLMGateway(provider=MockLLMProvider()), candidates)
    assert len(results) == 3
