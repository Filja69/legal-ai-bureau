"""initial schema — organizations, workspaces, legal knowledge base, matters, audit log

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-10

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("billing_tier", sa.Enum("free", "starter", "professional", "business", "bureau", "enterprise", name="billingtier"),
            nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Enum("owner", "admin", "lawyer", "paralegal", "analyst", "client", "viewer", name="rolename"), nullable=False,
            unique=True),
        sa.Column("description", sa.String(255)),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("jurisdiction", sa.String(8), server_default="RU"),
        sa.Column("country", sa.String(8), server_default="RU"),
        sa.Column("region", sa.String(64)),
        sa.Column("applicable_law", sa.String(255)),
        sa.Column("language", sa.String(8), server_default="ru"),
        sa.Column("kb_as_of_date", sa.String(16)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("mfa_enabled", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),
    )
    op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])

    # --- shared public legal knowledge base (no workspace_id — LEGAL-DATABASE.md §2) ---
    op.create_table(
        "legal_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.Enum("official_gov", "court", "tax", "commercial_db", "user_upload", name="sourcetype"), nullable=False),
        sa.Column("jurisdiction", sa.String(8), server_default="RU"),
        sa.Column("base_url", sa.String(512)),
        sa.Column("license_type", sa.String(64)),
        sa.Column("requires_license", sa.Boolean(), server_default=sa.false()),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "legal_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("document_type",
            sa.Enum("law", "code", "regulatory_act", "court_decision", "interpretation", "commercial_source", name="legaldocumenttype"),
            nullable=False),
        sa.Column("jurisdiction", sa.String(8), server_default="RU"),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_sources.id")),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("publication_date", sa.String(16)),
        sa.Column("effective_date", sa.String(16)),
        sa.Column("expiration_date", sa.String(16)),
        sa.Column("version", sa.String(32)),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("content", sa.Text()),
        sa.Column("doc_metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "laws",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_documents.id"), unique=True),
        sa.Column("short_name", sa.String(64), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("code_type", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "law_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("law_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("laws.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_number", sa.String(32)),
        sa.Column("clause_number", sa.String(32)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("amending_act_title", sa.String(512)),
        sa.Column("amending_act_source_url", sa.String(1024)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_law_versions_law_id", "law_versions", ["law_id"])
    op.create_index("ix_law_versions_validity", "law_versions", ["law_id", "valid_from", "valid_to"])

    op.create_table(
        "courts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("level", sa.Enum("supreme", "cassation", "appeal", "first_instance", name="courtlevel"), nullable=False),
        sa.Column("jurisdiction", sa.String(8), server_default="RU"),
        sa.Column("region", sa.String(128)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "court_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_documents.id"), unique=True),
        sa.Column("court_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courts.id"), nullable=False),
        sa.Column("case_number", sa.String(128), nullable=False),
        sa.Column("decision_date", sa.String(16)),
        sa.Column("parties", postgresql.JSONB(), server_default="{}"),
        sa.Column("claim_summary", sa.Text()),
        sa.Column("decision_summary", sa.Text()),
        sa.Column("legal_reasoning", sa.Text()),
        sa.Column("outcome", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_court_decisions_case_number", "court_decisions", ["case_number"])

    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("legal_documents.id"), nullable=False),
        sa.Column("cited_law_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("law_versions.id")),
        sa.Column("cited_court_decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("court_decisions.id")),
        sa.Column("quoted_fragment", sa.Text()),
        sa.Column("verification_status", sa.Enum("verified", "unverified", "broken", name="verificationstatus"),
            server_default="unverified"),
        sa.Column("last_verified_at", sa.String(32)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # --- tenant-scoped matter management (LEGAL-DATABASE.md §5) ---
    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum("open", "research", "drafting", "litigation", "closed", name="casestatus"), server_default="open"),
        sa.Column("client_name", sa.String(255)),
        sa.Column("counterparty_name", sa.String(255)),
        sa.Column("matter_type", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_cases_workspace_id", "cases", ["workspace_id"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("document_type", sa.Enum("contract", "evidence", "correspondence", "generated", "other", name="documenttype"),
            server_default="other"),
        sa.Column("storage_path", sa.String(1024)),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("doc_metadata", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_supported", sa.String(512), nullable=False),
        sa.Column("evidence_type", sa.String(64)),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id")),
        sa.Column("availability", sa.String(16), server_default="missing"),
        sa.Column("strength", sa.String(16)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_evidence_workspace_id", "evidence", ["workspace_id"])

    op.create_table(
        "legal_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE")),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("article_refs", postgresql.JSONB(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_legal_issues_workspace_id", "legal_issues", ["workspace_id"])

    op.create_table(
        "legal_risks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("clause_reference", sa.String(64)),
        sa.Column("severity", sa.Enum("low", "medium", "high", "critical", name="riskseverity"), nullable=False),
        sa.Column("probability", sa.String(16)),
        sa.Column("impact", sa.String(16)),
        sa.Column("category", sa.String(64)),
        sa.Column("explanation", sa.Text()),
        sa.Column("mitigation", sa.Text()),
        sa.Column("source_citation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("citations.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_legal_risks_workspace_id", "legal_risks", ["workspace_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("ai_model_used", sa.String(128)),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("sources_used", postgresql.JSONB(), server_default="[]"),
        sa.Column("result_summary", sa.Text()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])

    # --- Row-level security scaffold (LEGAL-SECURITY.md §2) ---
    # Policies are permissive-by-default here (USING true) until app/security/tenant.py
    # actually sets app.current_workspace_id on every request in Phase 2+; enabling a
    # restrictive policy before that wiring exists would just break local dev.
    # TODO(Phase 2): tighten each policy to
    #   USING (workspace_id = current_setting('app.current_workspace_id', true)::uuid)
    for table in ("cases", "documents", "evidence", "legal_issues", "legal_risks"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (true)")


def downgrade() -> None:
    for table in ("legal_risks", "legal_issues", "evidence", "documents", "cases"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_table("audit_logs")
    op.drop_table("legal_risks")
    op.drop_table("legal_issues")
    op.drop_table("evidence")
    op.drop_table("documents")
    op.drop_table("cases")
    op.drop_table("citations")
    op.drop_table("court_decisions")
    op.drop_table("courts")
    op.drop_table("law_versions")
    op.drop_table("laws")
    op.drop_table("legal_documents")
    op.drop_table("legal_sources")
    op.drop_table("workspace_memberships")
    op.drop_table("users")
    op.drop_table("workspaces")
    op.drop_table("roles")
    op.drop_table("organizations")

    for enum_name in (
        "riskseverity", "documenttype", "casestatus", "verificationstatus", "courtlevel",
        "legaldocumenttype", "sourcetype", "rolename", "billingtier",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
