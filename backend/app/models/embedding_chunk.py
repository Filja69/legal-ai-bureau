"""EmbeddingChunk — real pgvector-backed vector search index (LEGAL-DATABASE.md
§2/§7 originally described this, never modeled until Phase 2).

One row per embedded chunk of a `LawVersion` (or, later, other document
types) — polymorphic via `chunk_type`/`chunk_id` rather than a hard FK to
a single table, since search needs to span law text, court decisions, and
eventually user documents without a different table per type.
"""
from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config.settings import get_settings
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

_EMBEDDING_DIMENSION = get_settings().embedding_dimension


class EmbeddingChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "embedding_chunks"

    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "law_version" | "court_decision" | ...
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int | None] = mapped_column(Integer)

    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIMENSION), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)

    # Phase 5 additions (brief §21-22): `embedding_model` alone identifies
    # *what* produced the vector, but not *which provider* or which exact
    # revision — two providers could coincidentally use the same model name,
    # and a provider can silently update a model's weights under a stable
    # name. `embedding_provider` + `embedding_model_version` together are the
    # namespace key retrieval filters on, so switching models never silently
    # compares vectors that were never meant to be compared (brief §22).
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    embedding_model_version: Mapped[str | None] = mapped_column(String(64))
    # Phase 6: persisted `f"{provider}:{model}:{dimensions}"` (see
    # app.rag.embeddings.base.embedding_namespace) — a single indexed column
    # retrieval and reindex/activate operations filter on, instead of
    # recomputing a multi-column match on every query.
    embedding_namespace: Mapped[str] = mapped_column(String(200), nullable=False, default="mock:mock-embedding-v1:1536", index=True)

    # Denormalized retrieval-filter metadata (LEGAL-RAG.md §1 hybrid filtering) —
    # duplicated from the canonical row on purpose so metadata filtering doesn't
    # require a join against every possible chunk_type's table on every query.
    jurisdiction: Mapped[str | None] = mapped_column(String(8))
    document_type: Mapped[str | None] = mapped_column(String(32))
    law_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    law_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    article_number: Mapped[str | None] = mapped_column(String(32))
    court_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    effective_from: Mapped[str | None] = mapped_column(String(16))
    effective_to: Mapped[str | None] = mapped_column(String(16))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    is_mock: Mapped[bool] = mapped_column(default=False)

    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
