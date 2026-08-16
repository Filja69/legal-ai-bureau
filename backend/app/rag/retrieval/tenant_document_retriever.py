"""Tenant document retrieval — Phase 9.2 brief §16. Structurally distinct
from `PgVectorRetriever` (queries `EmbeddingChunk`, the public Legal
Knowledge Base, no `workspace_id` column at all): this retriever queries
`DocumentChunk`, which is workspace-scoped and NEVER queried without a
`workspace_id` filter — that filter is a required constructor argument
here, not something a caller can forget to pass (brief §16: "Нельзя
полагаться только на frontend filter").
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matters import DocumentChunk
from app.rag.embeddings.base import EmbeddingProvider, embedding_namespace


class TenantDocumentRetriever:
    def __init__(self, session: AsyncSession, embedding_provider: EmbeddingProvider) -> None:
        self._session = session
        self._embedding_provider = embedding_provider

    async def retrieve(
        self,
        *,
        workspace_id: uuid.UUID,
        query_text: str,
        document_ids: list[uuid.UUID] | None = None,
        top_k: int = 8,
    ) -> list[DocumentChunk]:
        if not query_text.strip():
            return []

        [query_embedding] = await self._embedding_provider.embed([query_text])
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)

        stmt = select(DocumentChunk, distance.label("distance")).where(
            DocumentChunk.workspace_id == workspace_id,
            DocumentChunk.embedding_namespace == embedding_namespace(self._embedding_provider),
        )
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        stmt = stmt.order_by(distance.asc()).limit(top_k)

        result = await self._session.execute(stmt)
        return [chunk for chunk, _distance in result.all()]
