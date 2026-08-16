"""Phase 5: embedding provider/version namespace + LegalSource.is_licensed

Revision ID: 0006_embedding_versioning
Revises: 0005_contract_review_perf
Create Date: 2026-08-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_embedding_versioning"
down_revision: str | None = "0005_contract_review_perf"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # Backfilled to "mock" for existing rows — every EmbeddingChunk in the
    # database today was in fact produced by MockEmbeddingProvider, so this
    # is a factual backfill, not a guess (brief §21-22 revision note).
    op.add_column("embedding_chunks", sa.Column("embedding_provider", sa.String(length=32), nullable=False, server_default="mock"))
    op.add_column("embedding_chunks", sa.Column("embedding_model_version", sa.String(length=64), nullable=True))
    op.alter_column("embedding_chunks", "embedding_provider", server_default=None)
    op.create_index(
        "ix_embedding_chunks_provider_model", "embedding_chunks", ["embedding_provider", "embedding_model"]
    )

    op.add_column("legal_sources", sa.Column("is_licensed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("legal_sources", "is_licensed", server_default=None)


def downgrade() -> None:
    op.drop_column("legal_sources", "is_licensed")
    op.drop_index("ix_embedding_chunks_provider_model", table_name="embedding_chunks")
    op.drop_column("embedding_chunks", "embedding_model_version")
    op.drop_column("embedding_chunks", "embedding_provider")
