"""Organization / Workspace / User / Role — the multi-tenancy backbone.

Organization -> Workspace -> {Case, Document, LegalResearchReport, ...}
See LEGAL-DATABASE.md §4 and LEGAL-SECURITY.md §1. There is no bare
`user_id` ownership anywhere in this schema — tenant data is always
reached through a workspace_id.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum


class BillingTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    BUSINESS = "business"
    BUREAU = "bureau"
    ENTERPRISE = "enterprise"


class RoleName(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    LAWYER = "lawyer"
    PARALEGAL = "paralegal"
    ANALYST = "analyst"
    CLIENT = "client"
    VIEWER = "viewer"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_tier: Mapped[BillingTier] = mapped_column(pg_enum(BillingTier), default=BillingTier.FREE)

    workspaces: Mapped[list[Workspace]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    users: Mapped[list[User]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Role(UUIDPrimaryKeyMixin, Base):
    """Lookup table for role names. Kept as a table (not a bare enum column)
    so future custom/organization-specific roles don't require a schema migration.
    """

    __tablename__ = "roles"

    name: Mapped[RoleName] = mapped_column(pg_enum(RoleName), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # LEGAL-PRD.md §3 — jurisdiction defaults
    jurisdiction: Mapped[str] = mapped_column(String(8), default="RU")
    country: Mapped[str] = mapped_column(String(8), default="RU")
    region: Mapped[str | None] = mapped_column(String(64))
    applicable_law: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(8), default="ru")
    kb_as_of_date: Mapped[str | None] = mapped_column(String(16))

    organization: Mapped[Organization] = relationship(back_populates="workspaces")
    memberships: Mapped[list[WorkspaceMembership]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(default=False)

    organization: Mapped[Organization] = relationship(back_populates="users")


class WorkspaceMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
