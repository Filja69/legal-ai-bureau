"""Phase 9.2: Document Intelligence — Document pipeline fields + document_chunks

Revision ID: 0009_document_intelligence
Revises: 0008_legal_research_reports
Create Date: 2026-08-14

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.config.settings import get_settings

revision: str = "0009_document_intelligence"
down_revision: str | None = "0008_legal_research_reports"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_EMBEDDING_DIMENSION = get_settings().embedding_dimension


def upgrade() -> None:
    op.add_column("documents", sa.Column("original_filename", sa.String(length=512), nullable=True))
    op.add_column("documents", sa.Column("media_type", sa.String(length=128), nullable=True))
    op.add_column("documents", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("sha256", sa.String(length=64), nullable=True))

    # Unlike op.create_table(), op.add_column() does NOT implicitly CREATE TYPE
    # for a Postgres enum — SQLAlchemy only auto-emits that DDL as part of a
    # CREATE TABLE compilation. Found this session via a real `alembic upgrade
    # head` run (docs/PHASE-9-2-INTEGRATION-VERIFICATION.md): the column add
    # failed with `UndefinedObjectError: type "documentstatus" does not
    # exist`, transactional DDL rolled the whole migration back cleanly, and
    # this was never actually applied anywhere before the fix below.
    document_status = sa.Enum(
        "uploaded", "processing", "ready", "failed", "ocr_required", "unsupported",
        name="documentstatus",
    )
    document_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "documents",
        sa.Column("status", document_status, nullable=False, server_default="uploaded"),
    )
    op.add_column("documents", sa.Column("processing_error", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_path", sa.String(length=512), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(_EMBEDDING_DIMENSION), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_namespace", sa.String(length=200), nullable=False),
        sa.UniqueConstraint("workspace_id", "document_id", "chunk_index", name="uq_document_chunk_position"),
    )
    op.create_index("ix_document_chunks_workspace_id", "document_chunks", ["workspace_id"])
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_embedding_namespace", "document_chunks", ["embedding_namespace"])

    # Same RLS scaffold as `documents`/`cases`/etc. in 0001 — permissive (USING true)
    # until app.current_workspace_id enforcement is tightened repo-wide (still an open
    # TODO from Phase 1, not this phase's scope); added here only for parity so
    # document_chunks isn't silently less protected than the table it belongs to.
    op.execute("ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY document_chunks_tenant_isolation ON document_chunks USING (true)")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS document_chunks_tenant_isolation ON document_chunks")
    op.drop_index("ix_document_chunks_embedding_namespace", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_workspace_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_column("documents", "processed_at")
    op.drop_column("documents", "processing_error")
    op.drop_column("documents", "status")
    op.drop_column("documents", "sha256")
    op.drop_column("documents", "size_bytes")
    op.drop_column("documents", "media_type")
    op.drop_column("documents", "original_filename")
    op.execute("DROP TYPE IF EXISTS documentstatus")
