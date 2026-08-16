"""Court / CourtDecision / Citation — see LEGAL-DATABASE.md §2, LEGAL-RAG.md §4.

Citation rows are written only by the Citation Validator
(app/rag/validation/citation_validator.py) — never hand-authored by an
agent — so verification_status is always the outcome of an actual check.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class CourtLevel(str, enum.Enum):
    SUPREME = "supreme"
    CASSATION = "cassation"
    APPEAL = "appeal"
    FIRST_INSTANCE = "first_instance"


class Court(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[CourtLevel] = mapped_column(pg_enum(CourtLevel), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), default="RU")
    region: Mapped[str | None] = mapped_column(String(128))


class CourtDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Extends LegalDocument (document_id) — see LEGAL-DATABASE.md."""

    __tablename__ = "court_decisions"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_documents.id"), unique=True)
    court_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courts.id"), nullable=False)
    case_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    decision_date: Mapped[str | None] = mapped_column(String(16))
    parties: Mapped[dict] = mapped_column(JSONB, default=dict)
    claim_summary: Mapped[str | None] = mapped_column(Text)
    decision_summary: Mapped[str | None] = mapped_column(Text)
    legal_reasoning: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(String(32))  # granted|denied|partial|settled


class VerificationStatus(str, enum.Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    BROKEN = "broken"


class Citation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Written exclusively by the Citation Validator (LEGAL-RAG.md §4)."""

    __tablename__ = "citations"

    source_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_documents.id"), nullable=False)
    cited_law_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("law_versions.id"))
    cited_court_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("court_decisions.id"))
    quoted_fragment: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[VerificationStatus] = mapped_column(pg_enum(VerificationStatus), default=VerificationStatus.UNVERIFIED)
    last_verified_at: Mapped[str | None] = mapped_column(String(32))
