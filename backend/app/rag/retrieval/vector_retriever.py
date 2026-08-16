"""Real pgvector cosine-similarity retrieval (brief §21, LEGAL-RAG.md §1)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_chunk import EmbeddingChunk
from app.rag.embeddings.base import EmbeddingProvider, embedding_namespace
from app.rag.retrieval.base import RetrievalQuery, RetrievedCandidate
from app.rag.retrieval.filters import apply_filters
from app.rag.retrieval.presentation import metadata_for, title_for


class PgVectorRetriever:
    mode = "semantic"

    def __init__(self, session: AsyncSession, embedding_provider: EmbeddingProvider) -> None:
        self._session = session
        self._embedding_provider = embedding_provider

    async def retrieve(self, query: RetrievalQuery) -> list[RetrievedCandidate]:
        if not query.text.strip():
            return []

        [query_embedding] = await self._embedding_provider.embed([query.text])
        distance = EmbeddingChunk.embedding.cosine_distance(query_embedding)

        stmt = select(EmbeddingChunk, distance.label("distance"))
        # Never compare vectors across embedding namespaces (brief §22) — a
        # query embedded with provider X can only be meaningfully compared
        # against chunks embedded with that same provider+model+dimensions.
        # Chunks from a prior/different model simply aren't candidates until
        # reindexed into the new namespace.
        stmt = stmt.where(EmbeddingChunk.embedding_namespace == embedding_namespace(self._embedding_provider))
        stmt = apply_filters(stmt, query)
        stmt = stmt.order_by(distance.asc()).limit(query.top_k)

        result = await self._session.execute(stmt)
        return [
            RetrievedCandidate(
                document_id=str(chunk.id),
                title=title_for(chunk),
                snippet=chunk.chunk_text[:280],
                score=1.0 - float(distance),  # cosine distance -> similarity
                retrieval_mode=self.mode,
                metadata=metadata_for(chunk),
            )
            for chunk, distance in result.all()
        ]
