"""Shared public Legal Knowledge Base — no workspace_id (LEGAL-DATABASE.md §2).

Temporal versioning is mandatory here: `Law` carries no free-standing
`text` column. Its content only exists through `LawVersion` rows, each
with a [valid_from, valid_to) window, so "what did this law say on date X"
is a query, never an assumption baked into a single mutable field.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import DDL, ForeignKey, String, Text, event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TemporalValidityMixin, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class SourceType(str, enum.Enum):
    OFFICIAL_GOV = "official_gov"
    COURT = "court"
    TAX = "tax"
    COMMERCIAL_DB = "commercial_db"
    USER_UPLOAD = "user_upload"


class LegalSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """See LEGAL-SOURCES.md — one row per connector-backed origin of legal content.

    Phase 2 revision (LEGAL-DATABASE.md revision note): added lifecycle +
    license/provenance fields the ingestion framework (app/knowledge/ingestion)
    needs to answer "is this source healthy" and "are we even allowed to
    index this" without guessing.
    """

    __tablename__ = "legal_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[SourceType] = mapped_column(pg_enum(SourceType), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(128))  # e.g. "pravo.gov.ru", "mock"
    jurisdiction: Mapped[str] = mapped_column(String(8), default="RU")
    base_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|disabled|error

    is_official: Mapped[bool] = mapped_column(default=False)
    is_mock: Mapped[bool] = mapped_column(default=False)
    # Phase 5 (brief §13) — official/licensed/public/free are independent
    # properties, not synonyms. A commercial database (КонсультантПлюс etc.)
    # can be `is_licensed=True, is_official=False`; a government open-data
    # portal can be `is_official=True, is_licensed=False` (no license needed).
    is_licensed: Mapped[bool] = mapped_column(default=False)

    # LEGAL-SOURCES.md §1/§15 — license posture gates ingestion, not an afterthought.
    license_type: Mapped[str | None] = mapped_column(String(64))
    license_terms_url: Mapped[str | None] = mapped_column(String(1024))
    license_status: Mapped[str] = mapped_column(String(16), default="unknown")  # known|unknown
    allowed_storage: Mapped[bool] = mapped_column(default=False)
    allowed_indexing: Mapped[bool] = mapped_column(default=False)
    allowed_derivatives: Mapped[bool] = mapped_column(default=False)
    requires_license: Mapped[bool] = mapped_column(default=False)

    last_sync_at: Mapped[str | None] = mapped_column(String(32))
    last_successful_sync_at: Mapped[str | None] = mapped_column(String(32))
    last_error: Mapped[str | None] = mapped_column(Text)


class LegalDocumentType(str, enum.Enum):
    LAW = "law"
    CODE = "code"
    REGULATORY_ACT = "regulatory_act"
    COURT_DECISION = "court_decision"
    INTERPRETATION = "interpretation"
    COMMERCIAL_SOURCE = "commercial_source"


class LegalDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Base row for anything ingested into the shared knowledge base."""

    __tablename__ = "legal_documents"

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[LegalDocumentType] = mapped_column(pg_enum(LegalDocumentType), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), default="RU")
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_sources.id"))
    source_url: Mapped[str | None] = mapped_column(String(1024))
    publication_date: Mapped[str | None] = mapped_column(String(16))
    effective_date: Mapped[str | None] = mapped_column(String(16))
    expiration_date: Mapped[str | None] = mapped_column(String(16))
    version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="active")  # active|superseded|repealed|draft
    content: Mapped[str | None] = mapped_column(Text)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)


class Law(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Extends LegalDocument (document_id) with law-specific identity fields."""

    __tablename__ = "laws"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_documents.id"), unique=True)
    short_name: Mapped[str] = mapped_column(String(64), nullable=False)  # "ГК РФ"
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    code_type: Mapped[str | None] = mapped_column(String(32))  # civil|tax|labor|criminal|administrative

    versions: Mapped[list[LawVersion]] = relationship(back_populates="law", cascade="all, delete-orphan")


class LawVersion(UUIDPrimaryKeyMixin, TimestampMixin, TemporalValidityMixin, Base):
    """A specific redaction of a Law/Article, valid for [valid_from, valid_to).

    This is the temporal-versioning core called out explicitly in
    LEGAL-ROADMAP.md Task #10 requirements: law text is never stored as a
    bare mutable field, only through versioned, dated rows. Also doubles as
    the "legal chunk" unit from brief §8 (Phase 2) — see the revision note
    at the top of LEGAL-DATABASE.md for why no separate Article/Clause/
    LegalChunk table was added on top of this one.
    """

    __tablename__ = "law_versions"

    law_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("laws.id", ondelete="CASCADE"), nullable=False, index=True)
    article_number: Mapped[str | None] = mapped_column(String(32))
    clause_number: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    amending_act_title: Mapped[str | None] = mapped_column(String(512))
    amending_act_source_url: Mapped[str | None] = mapped_column(String(1024))

    # Phase 2 additions:
    hierarchy_path: Mapped[list] = mapped_column(JSONB, default=list)  # e.g. ["ГК РФ", "Раздел III", "Глава 22", "Статья 309"]
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"))

    law: Mapped[Law] = relationship(back_populates="versions")


# Overlap prevention (LEGAL-DATABASE.md revision note, brief §10) is expressed
# as a Postgres EXCLUDE constraint over a generated `daterange` column.
# SQLAlchemy's declarative layer has no first-class support for either
# GENERATED ALWAYS AS columns or EXCLUDE constraints, so the authoritative
# definition lives in migrations/versions/0002_legal_kb_infra... — this
# event listener mirrors the *same* DDL onto `Base.metadata.create_all()`,
# which is what test fixtures (tests/conftest.py db_engine) use instead of
# running Alembic. If the constraint ever changes, update both places.
event.listen(
    LawVersion.__table__,
    "after_create",
    DDL("CREATE EXTENSION IF NOT EXISTS btree_gist"),
)
event.listen(
    LawVersion.__table__,
    "after_create",
    DDL(
        "ALTER TABLE law_versions ADD COLUMN validity daterange "
        "GENERATED ALWAYS AS (daterange(valid_from, valid_to, '[)')) STORED"
    ),
)
event.listen(
    LawVersion.__table__,
    "after_create",
    DDL(
        "ALTER TABLE law_versions ADD CONSTRAINT ex_law_versions_no_overlap "
        "EXCLUDE USING gist ("
        "  law_id WITH =, "
        "  coalesce(article_number, '') WITH =, "
        "  coalesce(clause_number, '') WITH =, "
        "  validity WITH &&"
        ")"
    ),
)
