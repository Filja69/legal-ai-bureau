"""contract intelligence — Contract/Version/Party/Clause/Obligation/Risk/
Recommendation/AlternativeClause/RedlineChange/Review, all tenant-scoped

Revision ID: 0004_contract_intel
Revises: 0003_embedding_chunk_fts
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_contract_intel"
down_revision: str | None = "0003_embedding_chunk_fts"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_TENANT_TABLES = (
    "contracts", "contract_versions", "contract_parties", "contract_clauses",
    "contract_obligations", "contract_risks", "contract_recommendations",
    "alternative_clauses", "redline_changes", "contract_reviews",
)


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id")),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("contract_type", sa.Enum(
            "service", "supply", "sale", "lease", "employment", "nda", "license", "loan", "agency",
            "distribution", "partnership", "software", "other", "unknown", name="contracttype",
        ), server_default="unknown"),
        sa.Column("contract_type_source", sa.Enum("ai_detected", "user_confirmed", "unknown", name="contracttypesource"),
            server_default="unknown"),
        sa.Column("governing_law", sa.String(64)),
        sa.Column("currency", sa.String(8)),
        sa.Column("language", sa.String(8), server_default="ru"),
        sa.Column("status", sa.Enum("draft", "analyzing", "analyzed", "analysis_failed", name="contractstatus"), server_default="draft"),
        sa.Column("contract_date", sa.String(16)),
        sa.Column("effective_date", sa.String(16)),
        sa.Column("expiration_date", sa.String(16)),
        sa.Column("is_mock", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contracts_workspace_id", "contracts", ["workspace_id"])

    op.create_table(
        "contract_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id")),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("is_current", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_versions_workspace_id", "contract_versions", ["workspace_id"])
    op.create_index("ix_contract_versions_contract_id", "contract_versions", ["contract_id"])

    op.create_table(
        "contract_parties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("party_type", sa.String(32)),
        sa.Column("role", sa.Enum(
            "customer", "supplier", "contractor", "employer", "employee", "landlord", "tenant",
            "licensor", "licensee", "other", name="partyrole",
        ), server_default="other"),
        sa.Column("inn", sa.String(32)),
        sa.Column("country", sa.String(8)),
        sa.Column("address", sa.String(1024)),
        sa.Column("signatory", sa.String(255)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_parties_workspace_id", "contract_parties", ["workspace_id"])
    op.create_index("ix_contract_parties_contract_id", "contract_parties", ["contract_id"])

    clause_type_enum = sa.Enum(
        "definitions", "subject", "price", "payment", "delivery", "acceptance", "warranty", "liability",
        "penalty", "indemnity", "force_majeure", "term", "renewal", "termination", "confidentiality",
        "personal_data", "intellectual_property", "license", "non_compete", "non_solicit",
        "dispute_resolution", "jurisdiction", "governing_law", "audit", "insurance", "assignment",
        "change_of_control", "notice", "other", name="clausetype",
    )
    op.create_table(
        "contract_clauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_clause_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_clauses.id")),
        sa.Column("clause_number", sa.String(32)),
        sa.Column("title", sa.String(255)),
        sa.Column("clause_type", clause_type_enum, server_default="other"),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("position_start", sa.Integer(), nullable=False),
        sa.Column("position_end", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_clauses_workspace_id", "contract_clauses", ["workspace_id"])
    op.create_index("ix_contract_clauses_contract_id", "contract_clauses", ["contract_id"])
    op.create_index("ix_contract_clauses_version_id", "contract_clauses", ["version_id"])

    op.create_table(
        "contract_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("party", sa.String(255)),
        sa.Column("action", sa.String(512), nullable=False),
        sa.Column("object", sa.String(512)),
        sa.Column("deadline", sa.String(255)),
        sa.Column("condition", sa.String(512)),
        sa.Column("consequence", sa.String(512)),
        sa.Column("obligation_type", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_obligations_workspace_id", "contract_obligations", ["workspace_id"])
    op.create_index("ix_contract_obligations_contract_id", "contract_obligations", ["contract_id"])

    op.create_table(
        "contract_risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_clauses.id")),
        sa.Column("risk_type", sa.Enum(
            "missing_protection", "ambiguity", "unfair_allocation", "unlimited_liability", "one_sided_termination",
            "payment_risk", "penalty_risk", "ip_risk", "confidentiality_risk", "data_protection_risk",
            "jurisdiction_risk", "dispute_risk", "renewal_risk", "assignment_risk", "change_of_control_risk",
            "compliance_risk", "other", name="risktype",
        ), nullable=False),
        sa.Column("severity", sa.Enum("critical", "high", "medium", "low", "info", name="contractriskseverity"), nullable=False),
        sa.Column("category", sa.Enum("legal", "commercial", "operational", "financial", "procedural", "compliance", name="riskcategory"),
            nullable=False),
        sa.Column("classification", sa.Enum(
            "illegal", "unenforceable", "high_risk", "unfavorable", "ambiguous", "missing_protection", name="riskclassification",
        ), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text()),
        sa.Column("legal_basis", sa.Text()),
        sa.Column("party_perspective", sa.Enum(
            "customer", "supplier", "landlord", "tenant", "employer", "employee", "licensor", "licensee", "neutral",
            name="partyperspective",
        ), server_default="neutral"),
        sa.Column("confidence", sa.String(16), server_default="low"),
        sa.Column("verification_status", sa.Enum("verified", "mock", "unverified", name="riskverificationstatus"),
            server_default="unverified"),
        sa.Column("research_id", sa.String(64)),
        sa.Column("citations", postgresql.JSONB(), server_default="[]"),
        sa.Column("agreement_status", sa.Enum("agreed", "disagreement", "requires_human_review", name="agreementstatus"),
            server_default="requires_human_review"),
        sa.Column("detector", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_risks_workspace_id", "contract_risks", ["workspace_id"])
    op.create_index("ix_contract_risks_contract_id", "contract_risks", ["contract_id"])

    op.create_table(
        "contract_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_risks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="3"),
        sa.Column("action", sa.Enum("keep", "negotiate", "rewrite", "remove", "add", name="recommendationaction"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("legal_basis", sa.Text()),
        sa.Column("commercial_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_recommendations_workspace_id", "contract_recommendations", ["workspace_id"])
    op.create_index("ix_contract_recommendations_risk_id", "contract_recommendations", ["risk_id"])

    op.create_table(
        "alternative_clauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_clause_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"),
            nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("proposed_text", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("legal_basis", sa.Text()),
        sa.Column("risk_reduction", sa.String(32)),
        sa.Column("commercial_tradeoff", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_alternative_clauses_workspace_id", "alternative_clauses", ["workspace_id"])

    op.create_table(
        "redline_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clause_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_risks.id")),
        sa.Column("alternative_clause_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alternative_clauses.id")),
        sa.Column("research_id", sa.String(64)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("diff_ops", postgresql.JSONB(), server_default="[]"),
        sa.Column("review_status", sa.Enum("proposed", "accepted", "rejected", name="redlinereviewstatus"), server_default="proposed"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_redline_changes_workspace_id", "redline_changes", ["workspace_id"])
    op.create_index("ix_redline_changes_contract_id", "redline_changes", ["contract_id"])

    op.create_table(
        "contract_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("party_perspective", sa.Enum(
            "customer", "supplier", "landlord", "tenant", "employer", "employee", "licensor", "licensee", "neutral",
            name="partyperspective", create_type=False,
        ), server_default="neutral"),
        sa.Column("review_depth", sa.Enum("quick", "standard", "detailed", "full_due_diligence", name="reviewdepth"),
            server_default="standard"),
        sa.Column("status", sa.Enum("running", "completed", "failed", name="contractreviewstatus"), server_default="running"),
        sa.Column("analysis_status", sa.Enum("current", "stale", name="analysisstatus"), server_default="current"),
        sa.Column("analysis_configuration_hash", sa.String(64), nullable=False),
        sa.Column("knowledge_snapshot", postgresql.JSONB(), server_default="{}"),
        sa.Column("executive_summary", sa.Text()),
        sa.Column("risk_summary", postgresql.JSONB(), server_default="{}"),
        sa.Column("overall_score", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_contract_reviews_workspace_id", "contract_reviews", ["workspace_id"])
    op.create_index("ix_contract_reviews_contract_id", "contract_reviews", ["contract_id"])
    op.create_index("ix_contract_reviews_config_hash", "contract_reviews", ["contract_id", "version_id", "analysis_configuration_hash"])

    # RLS scaffold (permissive today, tightened alongside app/security/tenant.py
    # wiring — same TODO as migrations 0001) for every new tenant table.
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (true)")


def downgrade() -> None:
    for table in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_table("contract_reviews")
    op.drop_table("redline_changes")
    op.drop_table("alternative_clauses")
    op.drop_table("contract_recommendations")
    op.drop_table("contract_risks")
    op.drop_table("contract_obligations")
    op.drop_table("contract_clauses")
    op.drop_table("contract_parties")
    op.drop_table("contract_versions")
    op.drop_table("contracts")

    for enum_name in (
        "contractreviewstatus", "analysisstatus", "reviewdepth", "redlinereviewstatus",
        "recommendationaction", "agreementstatus", "riskverificationstatus", "partyperspective",
        "riskclassification", "riskcategory", "contractriskseverity", "risktype", "clausetype",
        "partyrole", "contractstatus", "contracttypesource", "contracttype",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
