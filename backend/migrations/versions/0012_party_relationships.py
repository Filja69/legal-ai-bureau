"""Case Intelligence layer: party/corporate relationships, hypothesis
register, related litigation, and one new nullable FK on case_events so a
relationship-derived timeline entry has real provenance without a synthetic
CaseFact. Purely additive — no change to any existing table, enum, or the
E1-E4 tables/logic.

Revision ID: 0012_party_relationships
Revises: 0011_litigation_claims_payments
Create Date: 2026-08-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_party_relationships"
down_revision: str | None = "0011_litigation_claims_payments"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NEW_TABLES = ("case_party_relationships", "case_hypotheses", "case_related_litigation")


def upgrade() -> None:
    op.create_table(
        "case_party_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_party_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_parties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("related_party_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_parties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.Enum("director", "shareholder", "member", "other", name="relationshiptype"), nullable=False),
        sa.Column("ownership_percentage", sa.String(length=16), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "verification_status",
            sa.Enum("unverified", "document_supported", "externally_verified", "conflicting", name="relationshipverificationstatus"),
            nullable=False, server_default="unverified",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_case_party_relationships_workspace_id", "case_party_relationships", ["workspace_id"])
    op.create_index("ix_case_party_relationships_case_id", "case_party_relationships", ["case_id"])

    op.create_table(
        "case_hypotheses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "category", sa.Enum("fact", "counsel_hypothesis", "ai_inference", "missing_evidence", name="hypothesiscategory"),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("required_verification", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column(
            "related_relationship_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_party_relationships.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("source", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_case_hypotheses_workspace_id", "case_hypotheses", ["workspace_id"])
    op.create_index("ix_case_hypotheses_case_id", "case_hypotheses", ["case_id"])

    op.create_table(
        "case_related_litigation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("court", sa.String(length=255), nullable=True),
        sa.Column("case_number", sa.String(length=128), nullable=True),
        sa.Column("parties_description", sa.Text(), nullable=True),
        sa.Column("subject_matter", sa.Text(), nullable=True),
        sa.Column("amount_in_dispute", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_case_related_litigation_workspace_id", "case_related_litigation", ["workspace_id"])
    op.create_index("ix_case_related_litigation_case_id", "case_related_litigation", ["case_id"])

    op.add_column(
        "case_events",
        sa.Column(
            "source_relationship_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("case_party_relationships.id", ondelete="SET NULL"), nullable=True,
        ),
    )

    # Same permissive RLS scaffold as every other tenant table since 0001 —
    # parity, not new enforcement (still Phase 1's open TODO).
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (true)")


def downgrade() -> None:
    op.drop_column("case_events", "source_relationship_id")

    for table in _NEW_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_index("ix_case_related_litigation_case_id", table_name="case_related_litigation")
    op.drop_index("ix_case_related_litigation_workspace_id", table_name="case_related_litigation")
    op.drop_table("case_related_litigation")

    op.drop_index("ix_case_hypotheses_case_id", table_name="case_hypotheses")
    op.drop_index("ix_case_hypotheses_workspace_id", table_name="case_hypotheses")
    op.drop_table("case_hypotheses")
    op.execute("DROP TYPE IF EXISTS hypothesiscategory")

    op.drop_index("ix_case_party_relationships_case_id", table_name="case_party_relationships")
    op.drop_index("ix_case_party_relationships_workspace_id", table_name="case_party_relationships")
    op.drop_table("case_party_relationships")
    op.execute("DROP TYPE IF EXISTS relationshipverificationstatus")
    op.execute("DROP TYPE IF EXISTS relationshiptype")
