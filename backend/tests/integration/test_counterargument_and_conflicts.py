"""CounterArgumentAgent + LegalConflictDetector — brief §21, §26-28."""
from __future__ import annotations

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.domains.legal_research.conflict_detection import LegalConflictDetector
from app.domains.legal_research.counterargument import CounterArgumentAgent
from app.domains.legal_research.models import ConflictType, LegalIssue, QueryType, ResearchQuery
from app.domains.legal_research.retrieval_pipeline import MultiStageRetriever
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
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


@pytest.mark.asyncio
async def test_counterargument_agent_uses_fallback_query_under_mock_llm(db_session, indexed_dataset):
    agent = CounterArgumentAgent(db_session, LLMGateway(provider=MockLLMProvider()))
    issue = LegalIssue(id="1", title="односторонний отказ", description="d", priority=1)

    found = await agent.find(issue, conclusion="заказчик вправе отказаться", jurisdiction="RU", effective_at=None)

    assert isinstance(found, list)  # empty is a valid honest outcome; must not raise


@pytest.mark.asyncio
async def test_jurisprudential_conflict_detected_across_differing_outcomes(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="односторонний отказ", query_type=QueryType.COURT_PRACTICE, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[], top_k_per_query=10,
    )
    court_items = [i for i in pool.items if i.metadata.get("chunk_type") == "court_decision"]
    assert len(court_items) >= 2, "need at least 2 court decisions retrieved for this test to be meaningful"

    conflicts = await LegalConflictDetector(db_session).detect(pool.items)

    jurisprudential = [c for c in conflicts if c.conflict_type == ConflictType.JURISPRUDENTIAL_CONFLICT]
    assert len(jurisprudential) == 1
    assert jurisprudential[0].position_a != jurisprudential[0].position_b


@pytest.mark.asyncio
async def test_temporal_conflict_detected_when_both_redactions_present(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    # No effective_at pinned -> both ст. 309 redactions can surface.
    pool = await retriever.run(
        [ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[], top_k_per_query=10,
    )

    conflicts = await LegalConflictDetector(db_session).detect(pool.items)

    temporal = [c for c in conflicts if c.conflict_type == ConflictType.TEMPORAL_CONFLICT]
    assert len(temporal) >= 1


@pytest.mark.asyncio
async def test_no_conflict_when_effective_at_pins_single_redaction(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at="2025-06-01", facts=[], top_k_per_query=10,
    )

    conflicts = await LegalConflictDetector(db_session).detect(pool.items)
    temporal = [c for c in conflicts if c.conflict_type == ConflictType.TEMPORAL_CONFLICT]
    assert temporal == []


@pytest.mark.asyncio
async def test_no_jurisprudential_conflict_with_fewer_than_two_decisions(db_session, indexed_dataset):
    from app.domains.legal_research.models import EvidenceItem

    single = [
        EvidenceItem(
            source="s", citation="дело X", text="t", retrieval_score=1.0, retrieval_method=["exact"],
            metadata={"chunk_type": "court_decision", "court_decision_id": None},
        )
    ]
    conflicts = await LegalConflictDetector(db_session).detect(single)
    assert conflicts == []
