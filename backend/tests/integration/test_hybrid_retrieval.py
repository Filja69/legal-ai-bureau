"""Real keyword (Postgres FTS) + vector (pgvector) + hybrid retrieval, against
the mock dataset indexed through the actual ingestion pipeline — LEGAL-RAG.md
§1, brief §19-27.

MockEmbeddingProvider is deterministic but NOT semantic (LEGAL-RAG.md report
§12 REAL/MOCK split) — vector-search assertions here deliberately query with
the *exact* text of a target chunk (guaranteed near-zero cosine distance to
itself) rather than a paraphrase, since a paraphrase would only rank highly
under a real semantic embedding model.
"""
from __future__ import annotations

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.hybrid_retriever import HybridRetriever
from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever
from app.rag.retrieval.vector_retriever import PgVectorRetriever
from app.sources.mock.mock_source import MockLegalDataSource


@pytest.fixture
async def indexed_mock_dataset(db_session):
    source = LegalSource(name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, is_mock=True, is_official=False)
    db_session.add(source)
    await db_session.flush()

    embedding_provider = MockEmbeddingProvider()
    indexer = LegalChunkIndexer(db_session, embedding_provider)
    pipeline = IngestionPipeline(
        db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator(), indexer=indexer
    )
    await pipeline.ingest_source(source)
    await db_session.commit()
    return source, embedding_provider


@pytest.mark.asyncio
async def test_keyword_search_finds_relevant_article(db_session, indexed_mock_dataset):
    retriever = PostgresKeywordRetriever(db_session)
    results = await retriever.retrieve(RetrievalQuery(text="надлежащим образом", top_k=10))

    assert len(results) >= 1
    assert all(r.retrieval_mode == "exact" for r in results)
    assert any(r.metadata["article_number"] == "309" for r in results)


@pytest.mark.asyncio
async def test_keyword_search_finds_court_decision(db_session, indexed_mock_dataset):
    retriever = PostgresKeywordRetriever(db_session)
    results = await retriever.retrieve(RetrievalQuery(text="односторонний отказ", top_k=10))

    assert any(r.metadata["chunk_type"] == "court_decision" for r in results)


@pytest.mark.asyncio
async def test_keyword_search_respects_document_type_filter(db_session, indexed_mock_dataset):
    retriever = PostgresKeywordRetriever(db_session)
    results = await retriever.retrieve(
        RetrievalQuery(text="односторонний отказ", filters={"document_type": "law_article"}, top_k=10)
    )
    assert all(r.metadata["chunk_type"] != "court_decision" for r in results)


@pytest.mark.asyncio
async def test_keyword_search_empty_query_returns_nothing(db_session, indexed_mock_dataset):
    retriever = PostgresKeywordRetriever(db_session)
    results = await retriever.retrieve(RetrievalQuery(text="   ", top_k=10))
    assert results == []


@pytest.mark.asyncio
async def test_vector_search_ranks_identical_text_first(db_session, indexed_mock_dataset):
    from app.sources.mock.dataset import MOCK_LAW_ARTICLES

    target = next(r for r in MOCK_LAW_ARTICLES if r["external_id"] == "mock-gk-314")
    _, embedding_provider = indexed_mock_dataset

    retriever = PgVectorRetriever(db_session, embedding_provider)
    results = await retriever.retrieve(RetrievalQuery(text=target["text"], top_k=5))

    assert len(results) >= 1
    assert results[0].metadata["article_number"] == "314"
    assert results[0].score > 0.99  # near-identical embedding to itself


@pytest.mark.asyncio
async def test_vector_search_empty_query_returns_nothing(db_session, indexed_mock_dataset):
    _, embedding_provider = indexed_mock_dataset
    retriever = PgVectorRetriever(db_session, embedding_provider)
    results = await retriever.retrieve(RetrievalQuery(text="", top_k=5))
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_merges_both_legs(db_session, indexed_mock_dataset):
    from app.sources.mock.dataset import MOCK_LAW_ARTICLES

    target = next(r for r in MOCK_LAW_ARTICLES if r["external_id"] == "mock-gk-309-v2")
    _, embedding_provider = indexed_mock_dataset

    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, embedding_provider))
    results = await hybrid.retrieve(RetrievalQuery(text=target["text"], top_k=5))

    assert len(results) >= 1
    top = results[0]
    assert top.retrieval_mode == "hybrid"
    # The exact-text query should be found by both legs — keyword because the
    # words are literally present, vector because it's an identical embedding.
    assert set(top.metadata["matched_by"]) == {"exact", "semantic"}


@pytest.mark.asyncio
async def test_hybrid_search_effective_at_filters_out_superseded_version(db_session, indexed_mock_dataset):
    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, indexed_mock_dataset[1]))

    # "надлежащим образом" appears in both ст.309 redactions; pin to a date
    # only the OLD (2024-01-01..2025-01-01) redaction was in force for.
    results = await hybrid.retrieve(RetrievalQuery(text="надлежащим образом", event_date="2024-06-01", top_k=10))

    article_309_hits = [r for r in results if r.metadata.get("article_number") == "309"]
    assert len(article_309_hits) == 1
    assert article_309_hits[0].metadata["effective_to"] == "2025-01-01"


@pytest.mark.asyncio
async def test_hybrid_search_effective_at_selects_current_version(db_session, indexed_mock_dataset):
    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, indexed_mock_dataset[1]))

    results = await hybrid.retrieve(RetrievalQuery(text="надлежащим образом", event_date="2025-06-01", top_k=10))

    article_309_hits = [r for r in results if r.metadata.get("article_number") == "309"]
    assert len(article_309_hits) == 1
    assert article_309_hits[0].metadata["effective_to"] is None


@pytest.mark.asyncio
async def test_hybrid_search_top_k_is_respected(db_session, indexed_mock_dataset):
    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, indexed_mock_dataset[1]))
    results = await hybrid.retrieve(RetrievalQuery(text="обязательства", top_k=2))
    assert len(results) <= 2
