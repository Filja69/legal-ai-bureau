"""Phase 9.3: Litigation & Case Intelligence — bounded slice (parties,
case-document linking, facts-with-provenance, timeline, contradictions).

Revision ID: 0010_litigation_intelligence
Revises: 0009_document_intelligence
Create Date: 2026-08-16

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_litigation_intelligence"
down_revision: str | None = "0009_document_intelligence"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NEW_TABLES = (
    "case_parties",
    "case_documents",
    "case_facts",
    "case_fact_evidence",
    "case_events",
    "case_contradictions",
)


def upgrade() -> None:
    op.create_table(
        "case_parties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "party_type", sa.Enum("individual", "organization", "unknown", name="partytype"),
            nullable=False, server_default="unknown",
        ),
        sa.Column(
            "procedural_role",
            sa.Enum("plaintiff", "defendant", "third_party", "applicant", "respondent", "unknown", name="proceduralrole"),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("identifiers", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("party_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_case_parties_workspace_id", "case_parties", ["workspace_id"])
    op.create_index("ix_case_parties_case_id", "case_parties", ["case_id"])

    op.create_table(
        "case_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "contract", "addendum", "invoice", "act", "correspondence", "claim", "response",
                "court_filing", "court_decision", "expert_report", "payment_document", "other",
                name="casedocumentrole",
            ),
            nullable=False,
            server_default="other",
        ),
        sa.UniqueConstraint("case_id", "document_id", name="uq_case_document"),
    )
    op.create_index("ix_case_documents_workspace_id", "case_documents", ["workspace_id"])
    op.create_index("ix_case_documents_case_id", "case_documents", ["case_id"])
    op.create_index("ix_case_documents_document_id", "case_documents", ["document_id"])

    op.create_table(
        "case_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "fact_type", sa.Enum("date", "amount", "party", "event", "other", name="facttype"),
            nullable=False, server_default="other",
        ),
        sa.Column(
            "status",
            sa.Enum("asserted", "supported", "disputed", "contradicted", "inferred", "unknown", name="factstatus"),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("normalized_value", sa.String(length=128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
    )
    op.create_index("ix_case_facts_workspace_id", "case_facts", ["workspace_id"])
    op.create_index("ix_case_facts_case_id", "case_facts", ["case_id"])
    op.create_index("ix_case_facts_normalized_value", "case_facts", ["normalized_value"])

    op.create_table(
        "case_fact_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_fact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_path", sa.String(length=512), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=False),
    )
    op.create_index("ix_case_fact_evidence_workspace_id", "case_fact_evidence", ["workspace_id"])
    op.create_index("ix_case_fact_evidence_case_fact_id", "case_fact_evidence", ["case_fact_id"])

    op.create_table(
        "case_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column(
            "date_type", sa.Enum("exact", "calculated", "approximate", "unknown", name="datetype"),
            nullable=False, server_default="unknown",
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("source_fact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_facts.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_case_events_workspace_id", "case_events", ["workspace_id"])
    op.create_index("ix_case_events_case_id", "case_events", ["case_id"])

    op.create_table(
        "case_contradictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "contradiction_type",
            sa.Enum("date_mismatch", "amount_mismatch", "party_mismatch", "other", name="contradictiontype"),
            nullable=False,
            server_default="other",
        ),
        sa.Column("fact_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fact_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("case_facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_index("ix_case_contradictions_workspace_id", "case_contradictions", ["workspace_id"])
    op.create_index("ix_case_contradictions_case_id", "case_contradictions", ["case_id"])

    # Same permissive RLS scaffold as every other tenant table since 0001 —
    # parity, not new enforcement (still Phase 1's open TODO).
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (true)")


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_index("ix_case_contradictions_case_id", table_name="case_contradictions")
    op.drop_index("ix_case_contradictions_workspace_id", table_name="case_contradictions")
    op.drop_table("case_contradictions")
    op.execute("DROP TYPE IF EXISTS contradictiontype")

    op.drop_index("ix_case_events_case_id", table_name="case_events")
    op.drop_index("ix_case_events_workspace_id", table_name="case_events")
    op.drop_table("case_events")
    op.execute("DROP TYPE IF EXISTS datetype")

    op.drop_index("ix_case_fact_evidence_case_fact_id", table_name="case_fact_evidence")
    op.drop_index("ix_case_fact_evidence_workspace_id", table_name="case_fact_evidence")
    op.drop_table("case_fact_evidence")

    op.drop_index("ix_case_facts_normalized_value", table_name="case_facts")
    op.drop_index("ix_case_facts_case_id", table_name="case_facts")
    op.drop_index("ix_case_facts_workspace_id", table_name="case_facts")
    op.drop_table("case_facts")
    op.execute("DROP TYPE IF EXISTS factstatus")
    op.execute("DROP TYPE IF EXISTS facttype")

    op.drop_index("ix_case_documents_document_id", table_name="case_documents")
    op.drop_index("ix_case_documents_case_id", table_name="case_documents")
    op.drop_index("ix_case_documents_workspace_id", table_name="case_documents")
    op.drop_table("case_documents")
    op.execute("DROP TYPE IF EXISTS casedocumentrole")

    op.drop_index("ix_case_parties_case_id", table_name="case_parties")
    op.drop_index("ix_case_parties_workspace_id", table_name="case_parties")
    op.drop_table("case_parties")
    op.execute("DROP TYPE IF EXISTS proceduralrole")
    op.execute("DROP TYPE IF EXISTS partytype")
