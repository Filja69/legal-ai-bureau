"""Phase 8: persisted legal_research_reports table

Revision ID: 0008_legal_research_reports
Revises: 0007_embedding_namespace
Create Date: 2026-08-12

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_legal_research_reports"
down_revision: str | None = "0007_embedding_namespace"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "legal_research_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False, server_default="RU"),
        sa.Column(
            "status",
            sa.Enum("completed", "blocked_unverified_claim", "research_failed", name="researchreportstatus"),
            nullable=False,
        ),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("executive_conclusion", sa.Text(), nullable=False, server_default=""),
        sa.Column("escalate_to_human", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("trace_json", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_legal_research_reports_workspace_id", "legal_research_reports", ["workspace_id"])
    op.create_index("ix_legal_research_reports_case_id", "legal_research_reports", ["case_id"])
    op.create_index("ix_legal_research_reports_created_at", "legal_research_reports", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_legal_research_reports_created_at", table_name="legal_research_reports")
    op.drop_index("ix_legal_research_reports_case_id", table_name="legal_research_reports")
    op.drop_index("ix_legal_research_reports_workspace_id", table_name="legal_research_reports")
    op.drop_table("legal_research_reports")
    op.execute("DROP TYPE IF EXISTS researchreportstatus")
