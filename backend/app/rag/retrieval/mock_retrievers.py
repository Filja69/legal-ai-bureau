"""Mock retriever implementations — return clearly-labeled empty/placeholder
results so the retrieval router (LEGAL-RAG.md §2) and its callers can be
built/tested before real BM25+pgvector wiring lands in Phase 2.
"""
from __future__ import annotations

from app.rag.retrieval.base import (
    HybridRetriever,
    KeywordRetriever,
    RetrievalQuery,
    RetrievedCandidate,
    VectorRetriever,
)


class MockVectorRetriever(VectorRetriever):
    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]:
        return []


class MockKeywordRetriever(KeywordRetriever):
    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]:
        return []


class MockHybridRetriever(HybridRetriever):
    """Combines the mock vector + keyword legs — structurally correct composition,
    trivially empty results until Phase 2 backs each leg with a real index.
    """

    def __init__(self) -> None:
        self._vector = MockVectorRetriever()
        self._keyword = MockKeywordRetriever()

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]:
        vector_hits = await self._vector.retrieve(query)
        keyword_hits = await self._keyword.retrieve(query)
        return (vector_hits + keyword_hits)[: query.top_k]
