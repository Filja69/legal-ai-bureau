"""LegalEvidenceContext — brief §31-32. What actually gets handed to an LLM,
and the SOURCE_NOT_FOUND behavior when nothing verifiable exists.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.domains.legal_research.evidence_context import build_evidence_context
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.hybrid_retriever import HybridRetriever
from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever
from app.rag.retrieval.vector_retriever import PgVectorRetriever
from app.sources.mock.mock_source import MockLegalDataSource


@pytest.fixture
async def indexed_source(db_session):
    source = LegalSource(name="Mock", type=SourceType.USER_UPLOAD, is_mock=True)
    db_session.add(source)
    await db_session.flush()
    embedding_provider = MockEmbeddingProvider()
    indexer = LegalChunkIndexer(db_session, embedding_provider)
    pipeline = IngestionPipeline(
        db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator(), indexer=indexer
    )
    await pipeline.ingest_source(source)
    await db_session.commit()
    return embedding_provider


@pytest.mark.asyncio
async def test_evidence_context_admits_mock_sources_labeled_as_such(db_session, indexed_source):
    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, indexed_source))
    candidates = await hybrid.retrieve(RetrievalQuery(text="надлежащим образом", top_k=5))

    context = await build_evidence_context(db_session, "question", candidates)

    assert context.status == "ok"
    assert len(context.sources) >= 1
    assert all(s.is_mock for s in context.sources if s.status.value == "mock")


@pytest.mark.asyncio
async def test_evidence_context_source_not_found_when_no_candidates(db_session, indexed_source):
    context = await build_evidence_context(db_session, "question with no relevant law", [])
    assert context.status == "source_not_found"
    assert context.sources == []


@pytest.mark.asyncio
async def test_evidence_context_respects_effective_at(db_session, indexed_source):
    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, indexed_source))
    candidates = await hybrid.retrieve(RetrievalQuery(text="надлежащим образом", event_date="2024-06-01", top_k=5))

    context = await build_evidence_context(db_session, "question", candidates, effective_at=date(2024, 6, 1))

    assert context.effective_at == date(2024, 6, 1)
    assert context.status == "ok"
