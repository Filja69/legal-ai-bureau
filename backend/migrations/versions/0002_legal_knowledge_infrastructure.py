"""legal knowledge infrastructure — source lifecycle, provenance, embeddings, full-text search

Revision ID: 0002_legal_knowledge_infrastructure
Revises: 0001_initial_schema
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002_legal_kb_infra"
down_revision: str | None = "0001_initial_schema"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

EMBEDDING_DIMENSION = 1536  # must match Settings.embedding_dimension at migration time — see app/models/embedding_chunk.py


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # --- LegalSource lifecycle/license fields (LEGAL-SOURCES.md §15, brief §3) ---
    op.add_column("legal_sources", sa.Column("provider", sa.String(128)))
    op.add_column("legal_sources", sa.Column("is_official", sa.Boolean(), server_default=sa.false()))
    op.add_column("legal_sources", sa.Column("is_mock", sa.Boolean(), server_default=sa.false()))
    op.add_column("legal_sources", sa.Column("license_terms_url", sa.String(1024)))
    op.add_column("legal_sources", sa.Column("license_status", sa.String(16), server_default="unknown"))
    op.add_column("legal_sources", sa.Column("allowed_storage", sa.Boolean(), server_default=sa.false()))
    op.add_column("legal_sources", sa.Column("allowed_indexing", sa.Boolean(), server_default=sa.false()))
    op.add_column("legal_sources", sa.Column("allowed_derivatives", sa.Boolean(), server_default=sa.false()))
    op.add_column("legal_sources", sa.Column("last_sync_at", sa.String(32)))
    op.add_column("legal_sources", sa.Column("last_successful_sync_at", sa.String(32)))
    op.add_column("legal_sources", sa.Column("last_error", sa.Text()))

    op.create_index("ix_legal_documents_content_hash", "legal_documents", ["content_hash"])

    # --- SourceDocument: raw/normalized provenance staging (LEGAL-DATABASE.md revision note) ---
    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_sources.id"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("title", sa.String(512)),
        sa.Column("document_type", sa.String(32)),
        sa.Column("jurisdiction", sa.String(8), server_default="RU"),
        sa.Column("publication_date", sa.String(16)),
        sa.Column("effective_date", sa.String(16)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.String(32), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text()),
        sa.Column("source_metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("promoted_legal_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_documents.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_source_documents_source_id", "source_documents", ["source_id"])
    op.create_index("ix_source_documents_content_hash", "source_documents", ["content_hash"])
    # Idempotent ingestion (brief §17): the same source can never persist the same
    # content twice — re-running an ingestion job for an already-seen document is a
    # guaranteed no-op at the database level, not just app-level discipline.
    op.create_unique_constraint(
        "uq_source_documents_source_content_hash", "source_documents", ["source_id", "content_hash"]
    )

    # --- LawVersion: hierarchy + provenance link (LEGAL-DATABASE.md revision note) ---
    op.add_column("law_versions", sa.Column("hierarchy_path", postgresql.JSONB(), server_default="[]"))
    op.add_column(
        "law_versions", sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_documents.id"))
    )

    # --- Overlap prevention (brief §10/§41 — "two active versions of the same
    # norm at once" must be structurally impossible, not just app-level discipline).
    # daterange(valid_from, valid_to, '[)') treats a NULL valid_to as unbounded
    # ("still in force"), which is exactly the semantics LEGAL-DATABASE.md §3
    # documents. coalesce() on article/clause avoids NULL making the exclusion
    # a no-op for law-level (article-less) versions.
    op.execute(
        "ALTER TABLE law_versions ADD COLUMN validity daterange "
        "GENERATED ALWAYS AS (daterange(valid_from, valid_to, '[)')) STORED"
    )
    op.execute(
        "ALTER TABLE law_versions ADD CONSTRAINT ex_law_versions_no_overlap "
        "EXCLUDE USING gist ("
        "  law_id WITH =, "
        "  coalesce(article_number, '') WITH =, "
        "  coalesce(clause_number, '') WITH =, "
        "  validity WITH &&"
        ")"
    )

    # --- Full-text search (brief §20 — Postgres-native, no Elasticsearch) ---
    op.execute(
        "CREATE INDEX ix_law_versions_text_fts ON law_versions "
        "USING GIN (to_tsvector('russian', text))"
    )
    op.execute(
        "CREATE INDEX ix_legal_documents_content_fts ON legal_documents "
        "USING GIN (to_tsvector('russian', coalesce(content, '')))"
    )

    # --- EmbeddingChunk: real pgvector search index (LEGAL-DATABASE.md §2/§7) ---
    op.create_table(
        "embedding_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chunk_type", sa.String(32), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0"),
        sa.Column("token_count", sa.Integer()),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("jurisdiction", sa.String(8)),
        sa.Column("document_type", sa.String(32)),
        sa.Column("law_id", postgresql.UUID(as_uuid=True)),
        sa.Column("law_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("article_number", sa.String(32)),
        sa.Column("court_decision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("effective_from", sa.String(16)),
        sa.Column("effective_to", sa.String(16)),
        sa.Column("source_id", postgresql.UUID(as_uuid=True)),
        sa.Column("is_mock", sa.Boolean(), server_default=sa.false()),
        sa.Column("chunk_metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_embedding_chunks_chunk_id", "embedding_chunks", ["chunk_id"])
    op.create_index("ix_embedding_chunks_law_id", "embedding_chunks", ["law_id"])
    op.create_index("ix_embedding_chunks_law_version_id", "embedding_chunks", ["law_version_id"])
    op.create_index("ix_embedding_chunks_court_decision_id", "embedding_chunks", ["court_decision_id"])
    op.create_index("ix_embedding_chunks_source_id", "embedding_chunks", ["source_id"])
    # ivfflat requires an initial data population to pick good `lists`; with an
    # empty/small mock-scale table at this stage, HNSW's build-time behavior is
    # more forgiving. Revisit index type/params once real corpus volume exists
    # (LEGAL-ROADMAP.md Phase 2 exit criterion).
    op.execute(
        "CREATE INDEX ix_embedding_chunks_embedding_hnsw ON embedding_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_embedding_chunks_embedding_hnsw", table_name="embedding_chunks")
    op.drop_table("embedding_chunks")

    op.execute("DROP INDEX IF EXISTS ix_legal_documents_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_law_versions_text_fts")

    # Phase 6.5 fix: alembic's op.drop_constraint(type_=...) only accepts
    # 'check'/'foreignkey'/'primary'/'unique'/None — it has no literal for a
    # Postgres EXCLUDE constraint, so this must be raw SQL (found by the
    # Phase 6.5 fresh-db upgrade/downgrade/upgrade audit — downgrade had
    # never actually been exercised against a real database before).
    op.execute("ALTER TABLE law_versions DROP CONSTRAINT ex_law_versions_no_overlap")
    op.drop_column("law_versions", "validity")
    op.drop_column("law_versions", "source_document_id")
    op.drop_column("law_versions", "hierarchy_path")

    op.drop_constraint("uq_source_documents_source_content_hash", "source_documents", type_="unique")
    op.drop_table("source_documents")

    op.drop_index("ix_legal_documents_content_hash", table_name="legal_documents")

    for col in (
        "last_error", "last_successful_sync_at", "last_sync_at", "allowed_derivatives",
        "allowed_indexing", "allowed_storage", "license_status", "license_terms_url",
        "is_mock", "is_official", "provider",
    ):
        op.drop_column("legal_sources", col)
