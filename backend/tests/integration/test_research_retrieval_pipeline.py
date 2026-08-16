"""MultiStageRetriever + EvidenceRanker against the real (mock) Knowledge Base
— Phase 3 brief §11-15.
"""
from __future__ import annotations

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.domains.legal_research.evidence_ranking import EvidenceRanker
from app.domains.legal_research.models import AuthorityLevel, QueryType, ResearchQuery
from app.domains.legal_research.retrieval_pipeline import MultiStageRetriever
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
async def test_multi_stage_retriever_finds_law_articles(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    queries = [ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1")]

    pool = await retriever.run(queries, jurisdiction="RU", effective_at=None, facts=[])

    assert len(pool.items) >= 1
    assert any(i.metadata.get("article_number") == "309" for i in pool.items)


@pytest.mark.asyncio
async def test_multi_stage_retriever_court_practice_pass(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    queries = [ResearchQuery(text="односторонний отказ", query_type=QueryType.COURT_PRACTICE, issue_id="1")]

    pool = await retriever.run(queries, jurisdiction="RU", effective_at=None, facts=[])

    assert any(i.metadata.get("chunk_type") == "court_decision" for i in pool.items)


@pytest.mark.asyncio
async def test_multi_stage_retriever_interpretation_pass_is_honestly_empty(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    queries = [ResearchQuery(text="официальное разъяснение", query_type=QueryType.LEGAL_POSITION, issue_id="1")]

    pool = await retriever.run(queries, jurisdiction="RU", effective_at=None, facts=[])

    # No `interpretation` documents exist in the mock KB — must not fabricate any.
    assert not any(i.metadata.get("document_type") == "interpretation" for i in pool.items)


@pytest.mark.asyncio
async def test_multi_stage_retriever_deduplicates_across_passes(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    queries = [
        ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1"),
        ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1"),
    ]

    pool = await retriever.run(queries, jurisdiction="RU", effective_at=None, facts=[])
    chunk_ids = [i.chunk_id for i in pool.items]
    assert len(chunk_ids) == len(set(chunk_ids))


@pytest.mark.asyncio
async def test_multi_stage_retriever_fact_specific_pass(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run([], jurisdiction="RU", effective_at=None, facts=["односторонний отказ от договора поставки"])
    assert len(pool.items) >= 1


@pytest.mark.asyncio
async def test_evidence_ranker_marks_mock_items_with_mock_authority(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[],
    )

    ranked = await EvidenceRanker(db_session).rank(pool)

    assert len(ranked.items) >= 1
    assert all(item.authority == AuthorityLevel.MOCK for item in ranked.items)


@pytest.mark.asyncio
async def test_evidence_ranker_sorts_by_relevance_descending(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="обязательства", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[],
    )
    ranked = await EvidenceRanker(db_session).rank(pool)

    relevances = [i.relevance for i in ranked.items]
    assert relevances == sorted(relevances, reverse=True)


@pytest.mark.asyncio
async def test_evidence_pool_unique_documents_property(db_session, indexed_dataset):
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="обязательства", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[], top_k_per_query=10,
    )
    assert len(pool.unique_documents) >= 1
