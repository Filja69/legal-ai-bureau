"""contract_reviews.performance_ms — brief §58 performance instrumentation

Revision ID: 0005_contract_review_perf
Revises: 0004_contract_intel
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_contract_review_perf"
down_revision: str | None = "0004_contract_intel"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column("contract_reviews", sa.Column("performance_ms", postgresql.JSONB(), server_default="{}"))


def downgrade() -> None:
    op.drop_column("contract_reviews", "performance_ms")
