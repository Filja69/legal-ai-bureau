"""Phase 6: persisted embedding_namespace column on embedding_chunks

Revision ID: 0007_embedding_namespace
Revises: 0006_embedding_versioning
Create Date: 2026-08-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_embedding_namespace"
down_revision: str | None = "0006_embedding_versioning"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        "embedding_chunks",
        sa.Column("embedding_namespace", sa.String(length=200), nullable=False, server_default="mock:mock-embedding-v1:1536"),
    )
    # Backfill from the actual per-row provider/model/dimension columns added
    # in 0006 — not the server_default above, which only covers legacy rows
    # that predate 0006 too (and were already backfilled to "mock" there).
    op.execute(
        "UPDATE embedding_chunks SET embedding_namespace = "
        "embedding_provider || ':' || embedding_model || ':' || embedding_dimension::text"
    )
    op.alter_column("embedding_chunks", "embedding_namespace", server_default=None)
    op.create_index("ix_embedding_chunks_embedding_namespace", "embedding_chunks", ["embedding_namespace"])
    op.drop_index("ix_embedding_chunks_provider_model", table_name="embedding_chunks")


def downgrade() -> None:
    op.create_index("ix_embedding_chunks_provider_model", "embedding_chunks", ["embedding_provider", "embedding_model"])
    op.drop_index("ix_embedding_chunks_embedding_namespace", table_name="embedding_chunks")
    op.drop_column("embedding_chunks", "embedding_namespace")
