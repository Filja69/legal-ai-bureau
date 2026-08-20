"""Litigation evidence layer: case allegations (claims found in a party's
own pleading text) and structured payment-order facts (E1/E3 of the
curated-dataset-task companion brief). CLAIM_VS_EVIDENCE contradictions are
computed at read time from these two tables, never persisted — no change
to case_contradictions or its contradictiontype enum.

Revision ID: 0011_litigation_claims_payments
Revises: 0010_litigation_intelligence
Create Date: 2026-08-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_litigation_claims_payments"
down_revision: str | None = "0010_litigation_intelligence"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NEW_TABLES = ("case_allegations", "case_payment_orders")


def upgrade() -> None:
    op.create_table(
        "case_allegations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("statement_text", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column(
            "allegation_type",
            sa.Enum(
                "no_contract", "no_legal_basis", "unjust_enrichment", "payment_by_mistake", "future_contract_negotiations",
                name="allegationtype",
            ),
            nullable=False,
        ),
    )
    op.create_index("ix_case_allegations_workspace_id", "case_allegations", ["workspace_id"])
    op.create_index("ix_case_allegations_case_id", "case_allegations", ["case_id"])

    op.create_table(
        "case_payment_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.String(length=32), nullable=True),
        sa.Column("payer", sa.String(length=255), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=True),
        sa.Column("payment_purpose", sa.Text(), nullable=True),
        sa.Column("referenced_contract_type", sa.String(length=128), nullable=True),
        sa.Column("referenced_contract_date", sa.Date(), nullable=True),
        sa.Column("referenced_contract_number", sa.String(length=64), nullable=True),
        sa.Column(
            "execution_status", sa.Enum("executed", "unknown", name="paymentexecutionstatus"),
            nullable=False, server_default="unknown",
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
    )
    op.create_index("ix_case_payment_orders_workspace_id", "case_payment_orders", ["workspace_id"])
    op.create_index("ix_case_payment_orders_case_id", "case_payment_orders", ["case_id"])

    # Same permissive RLS scaffold as every other tenant table since 0001 —
    # parity, not new enforcement (still Phase 1's open TODO).
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (true)")


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_index("ix_case_payment_orders_case_id", table_name="case_payment_orders")
    op.drop_index("ix_case_payment_orders_workspace_id", table_name="case_payment_orders")
    op.drop_table("case_payment_orders")
    op.execute("DROP TYPE IF EXISTS paymentexecutionstatus")

    op.drop_index("ix_case_allegations_case_id", table_name="case_allegations")
    op.drop_index("ix_case_allegations_workspace_id", table_name="case_allegations")
    op.drop_table("case_allegations")
    op.execute("DROP TYPE IF EXISTS allegationtype")
