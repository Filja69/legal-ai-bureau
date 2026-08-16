"""embedding_chunks full-text index — unifies keyword + vector search on one table

Revision ID: 0003_embedding_chunk_fts
Revises: 0002_legal_kb_infra
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_embedding_chunk_fts"
down_revision: str | None = "0002_legal_kb_infra"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # embedding_chunks.chunk_text mirrors the canonical LawVersion.text /
    # CourtDecision.legal_reasoning at index time (LEGAL-RAG.md §1) — hybrid
    # search runs BOTH keyword and vector retrieval against this one table
    # instead of stitching results across per-type tables.
    op.execute(
        "CREATE INDEX ix_embedding_chunks_text_fts ON embedding_chunks "
        "USING GIN (to_tsvector('russian', chunk_text))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embedding_chunks_text_fts")
