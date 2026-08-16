"""Two-lawyer review — brief §32-34."""
from __future__ import annotations

import pytest

from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.domains.contracts.two_lawyer_review import two_lawyer_review
from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import AgreementStatus, ContractType
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource

_RISKY_CONTRACT = """1. Предмет договора

1.1. Исполнитель обязуется оказать услуги, а Заказчик обязуется принять и оплатить услуги.

3. Ответственность сторон

3.1. Ответственность Исполнителя перед Заказчиком не ограничивается и наступает в полном объеме, включая косвенные убытки.

4. Расторжение

4.1. Заказчик вправе отказаться от исполнения договора в любое время без уведомления и без объяснения причин.
"""


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


@pytest.mark.asyncio
async def test_two_lawyer_review_agrees_on_deterministic_detectors(db_session, indexed_dataset):
    clauses = ContractStructureExtractor().extract(_RISKY_CONTRACT)
    outcome = await two_lawyer_review(db_session, LLMGateway(provider=MockLLMProvider()), clauses, ContractType.SERVICE)

    assert outcome.analyst_count == outcome.reviewer_count
    assert outcome.analyst_count > 0
    assert all(r.agreement_status == AgreementStatus.AGREED for r in outcome.risks)


@pytest.mark.asyncio
async def test_two_lawyer_review_covers_all_analyst_findings(db_session, indexed_dataset):
    clauses = ContractStructureExtractor().extract(_RISKY_CONTRACT)
    outcome = await two_lawyer_review(db_session, LLMGateway(provider=MockLLMProvider()), clauses, ContractType.SERVICE)

    assert len(outcome.risks) >= outcome.analyst_count


@pytest.mark.asyncio
async def test_two_lawyer_review_clean_contract_yields_fewer_risks(db_session, indexed_dataset):
    clean_text = "1. Предмет договора\n\n1.1. Исполнитель оказывает услуги надлежащим образом.\n"
    clauses = ContractStructureExtractor().extract(clean_text)
    outcome = await two_lawyer_review(db_session, LLMGateway(provider=MockLLMProvider()), clauses, ContractType.NDA)

    risky_clauses = ContractStructureExtractor().extract(_RISKY_CONTRACT)
    risky_outcome = await two_lawyer_review(db_session, LLMGateway(provider=MockLLMProvider()), risky_clauses, ContractType.SERVICE)

    assert outcome.analyst_count <= risky_outcome.analyst_count
