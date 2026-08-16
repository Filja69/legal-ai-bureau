"""HybridRetriever — the default retrieval path for open questions (LEGAL-RAG.md
§1, brief §24).

```
Query -> keyword retrieval + vector retrieval (parallel legs, same filters)
      -> candidate merge (reciprocal rank fusion)
      -> deduplication (same chunk found by both legs)
      -> reranking
      -> top K
```
"""
from __future__ import annotations

import time

from app.core.logging import get_logger
from app.rag.reranking.base import MockReranker
from app.rag.retrieval.base import RetrievalQuery, RetrievedCandidate, Retriever

_RRF_K = 60  # standard reciprocal-rank-fusion constant
_logger = get_logger(__name__)


class HybridRetriever:
    mode = "hybrid"

    def __init__(self, keyword_retriever: Retriever, vector_retriever: Retriever, reranker: MockReranker | None = None) -> None:
        self._keyword = keyword_retriever
        self._vector = vector_retriever
        self._reranker = reranker or MockReranker()

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]:
        total_start = time.perf_counter()
        # Retrieve a wider candidate pool per leg than the final top_k so
        # fusion has something to fuse — mirrors standard hybrid-search practice.
        wide_query = RetrievalQuery(
            text=query.text, jurisdiction=query.jurisdiction, event_date=query.event_date,
            filters=query.filters, top_k=max(query.top_k * 3, 30),
        )
        # Sequential, not asyncio.gather: both legs are typically handed the
        # same AsyncSession (one per request), and SQLAlchemy's async Session
        # is not safe for concurrent use from two coroutines at once.
        keyword_start = time.perf_counter()
        keyword_results = await self._keyword.retrieve(wide_query)
        keyword_ms = (time.perf_counter() - keyword_start) * 1000

        vector_start = time.perf_counter()
        vector_results = await self._vector.retrieve(wide_query)
        vector_ms = (time.perf_counter() - vector_start) * 1000

        fused = _reciprocal_rank_fusion(keyword_results, vector_results)

        rerank_start = time.perf_counter()
        reranked = await self._reranker.rerank(query, fused)
        rerank_ms = (time.perf_counter() - rerank_start) * 1000

        final = reranked[: query.top_k]
        total_ms = (time.perf_counter() - total_start) * 1000

        # Structured retrieval observability (Phase 6 brief §13) — metadata
        # and timings only, never the query text's legal substance beyond
        # what's already logged elsewhere at the API layer, and never chain
        # of thought (there is none here — this is retrieval mechanics).
        _logger.info(
            "hybrid_retrieval",
            keyword_latency_ms=round(keyword_ms, 2),
            vector_latency_ms=round(vector_ms, 2),
            reranker_latency_ms=round(rerank_ms, 2),
            retrieval_latency_ms=round(total_ms, 2),
            keyword_candidate_count=len(keyword_results),
            vector_candidate_count=len(vector_results),
            fused_candidate_count=len(fused),
            results_count=len(final),
        )
        return final


def _reciprocal_rank_fusion(
    keyword_results: list[RetrievedCandidate], vector_results: list[RetrievedCandidate]
) -> list[RetrievedCandidate]:
    scores: dict[str, float] = {}
    by_id: dict[str, RetrievedCandidate] = {}
    modes_by_id: dict[str, set[str]] = {}

    for results in (keyword_results, vector_results):
        for rank, candidate in enumerate(results, start=1):
            scores[candidate.document_id] = scores.get(candidate.document_id, 0.0) + 1.0 / (_RRF_K + rank)
            by_id.setdefault(candidate.document_id, candidate)
            modes_by_id.setdefault(candidate.document_id, set()).add(candidate.retrieval_mode)

    fused: list[RetrievedCandidate] = []
    for document_id, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        base = by_id[document_id]
        fused.append(
            RetrievedCandidate(
                document_id=document_id,
                title=base.title,
                snippet=base.snippet,
                score=score,
                retrieval_mode="hybrid",
                metadata={**base.metadata, "matched_by": sorted(modes_by_id[document_id])},
            )
        )
    return fused
