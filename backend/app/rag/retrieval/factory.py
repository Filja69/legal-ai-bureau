"""Wires the real retrieval stack together for API routes — the one place
that knows PostgresKeywordRetriever + PgVectorRetriever + HybridRetriever
get composed this way, so routes stay thin.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.embeddings.base import get_embedding_provider
from app.rag.retrieval.hybrid_retriever import HybridRetriever
from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever
from app.rag.retrieval.vector_retriever import PgVectorRetriever


def build_hybrid_retriever(session: AsyncSession) -> HybridRetriever:
    embedding_provider = get_embedding_provider()
    return HybridRetriever(PostgresKeywordRetriever(session), PgVectorRetriever(session, embedding_provider))
