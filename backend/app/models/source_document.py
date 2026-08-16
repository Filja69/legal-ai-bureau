"""SourceDocument — raw/normalized provenance staging record (LEGAL-DATABASE.md
Phase 2 revision note; brief §4-5).

An ingestion run always creates a SourceDocument *first*, from whatever
LegalDataSource.fetch() returned, before anything is promoted into the
canonical LegalDocument/Law/LawVersion tables. This is what lets every
canonical row answer "where did this text actually come from" — source,
URL, retrieval time, hash, raw vs normalized content — without those
staging concerns leaking into the canonical schema.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_documents"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_sources.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    title: Mapped[str | None] = mapped_column(String(512))
    document_type: Mapped[str | None] = mapped_column(String(32))
    jurisdiction: Mapped[str] = mapped_column(String(8), default="RU")
    publication_date: Mapped[str | None] = mapped_column(String(16))
    effective_date: Mapped[str | None] = mapped_column(String(16))

    # LEGAL-SOURCES.md §17 — deterministic SHA-256 over normalized_content,
    # the dedup/idempotency/change-detection key for the whole ingestion pipeline.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    retrieved_at: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str | None] = mapped_column(Text)
    source_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Set once this staging record has been promoted into the canonical KB.
    promoted_legal_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_documents.id"))
