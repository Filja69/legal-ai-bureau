"""Real Postgres full-text (BM25-ish, via ts_rank) keyword retrieval (brief §20).

No Elasticsearch — `to_tsvector('russian', chunk_text) @@ to_tsquery(...)`
against the GIN index created in migration 0003_embedding_chunk_fts.

Query lexemes are OR-ed together (via tsvector_to_array + array_to_string),
not AND-ed like `plainto_tsquery`'s default: a natural-language legal
question ("надлежащее исполнение обязательства по договору поставки") is a
recall query, not a boolean filter — a document matching 3 of 4 concepts
should still surface, just ranked below one matching all 4. `ts_rank`
already rewards matching more/rarer terms, so OR-with-ranking beats a hard
AND that returns nothing the moment one word isn't present verbatim.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_chunk import EmbeddingChunk
from app.rag.retrieval.base import RetrievalQuery, RetrievedCandidate
from app.rag.retrieval.filters import apply_filters
from app.rag.retrieval.presentation import metadata_for, title_for


class PostgresKeywordRetriever:
    mode = "exact"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]:
        if not query.text.strip():
            return []

        query_lexemes = func.tsvector_to_array(func.to_tsvector("russian", query.text))
        or_joined_lexemes = func.array_to_string(query_lexemes, " | ")
        tsquery = func.to_tsquery("russian", or_joined_lexemes)
        tsvector = func.to_tsvector("russian", EmbeddingChunk.chunk_text)
        rank = func.ts_rank(tsvector, tsquery)

        stmt = select(EmbeddingChunk, rank.label("score")).where(tsvector.op("@@")(tsquery))
        stmt = apply_filters(stmt, query)
        stmt = stmt.order_by(rank.desc()).limit(query.top_k)

        result = await self._session.execute(stmt)
        return [
            RetrievedCandidate(
                document_id=str(chunk.id),
                title=title_for(chunk),
                snippet=chunk.chunk_text[:280],
                score=float(score),
                retrieval_mode=self.mode,
                metadata=metadata_for(chunk),
            )
            for chunk, score in result.all()
        ]
