"""Reranker interface + a no-op mock (LEGAL-RAG.md §1)."""
from __future__ import annotations

from app.rag.retrieval.base import RetrievalQuery, RetrievedCandidate


class MockReranker:
    """Identity reranker — preserves input order. Real cross-encoder/LLM
    reranking is Phase 2 work.
    """

    async def rerank(self, query: RetrievalQuery, candidates: list[RetrievedCandidate]) -> list[RetrievedCandidate]:
        return candidates
