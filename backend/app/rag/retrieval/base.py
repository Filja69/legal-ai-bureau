"""Retrieval interfaces (LEGAL-RAG.md §1-2). Mock-backed at scaffold stage;
real BM25/vector/rerank implementations land in Phase 2 (Core Engine).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class RetrievedCandidate:
    document_id: str
    title: str
    snippet: str
    score: float
    retrieval_mode: str  # semantic|exact|citation|temporal|case_law|hybrid
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalQuery:
    text: str
    jurisdiction: str = "RU"
    event_date: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)
    top_k: int = 10


class Retriever(Protocol):
    """Base contract every retrieval mode implements."""

    mode: str

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]: ...


class VectorRetriever(Retriever):
    """Semantic retrieval over EmbeddingChunk (pgvector cosine)."""

    mode = "semantic"


class KeywordRetriever(Retriever):
    """BM25 / Postgres ts_rank full-text retrieval — the exact/lexical leg of hybrid search."""

    mode = "exact"


class HybridRetriever(Retriever):
    """BM25 + Vector + metadata filtering + reranking (LEGAL-RAG.md §1)."""

    mode = "hybrid"


class Reranker(Protocol):
    """Cross-encoder or LLM-based reranking of top-K candidates from HybridRetriever."""

    async def rerank(self, query: RetrievalQuery, candidates: list[RetrievedCandidate]) -> list[RetrievedCandidate]: ...
