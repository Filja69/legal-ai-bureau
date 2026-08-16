"""Shared model mixins: UUID PK, timestamps, tenant scoping, temporal validity."""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import TypeVar

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

_EnumT = TypeVar("_EnumT", bound=enum.Enum)


def pg_enum(enum_cls: type[_EnumT], **kwargs) -> Enum:
    """SQLAlchemy's Enum() stores the Python member's `.name` by default (e.g.
    "OPEN"), but every enum in this codebase deliberately has lowercase
    `.value`s ("open") to match the Postgres enum type Alembic creates and to
    keep API/JSON payloads lowercase. Without `values_callable`, inserts fail
    with "invalid input value for enum ...: OPEN". Use this helper instead of
    bare `Enum(...)` on every enum-backed column.
    """
    return Enum(enum_cls, values_callable=lambda x: [e.value for e in x], **kwargs)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class WorkspaceScopedMixin:
    """Every tenant-owned table gets this. app/repositories/* must always filter on
    workspace_id explicitly (defense layer 1); Postgres RLS policies key off the same
    column via the session-local GUC set in app/db/session.py (defense layer 2).
    See LEGAL-SECURITY.md §2.
    """

    @property
    def workspace_id_column(self):  # pragma: no cover - documentation helper
        return "workspace_id"


class TemporalValidityMixin:
    """valid_from/valid_to for norm-bearing rows (Article, LawVersion, LegalPosition).

    NULL valid_to means "still in force". See LEGAL-DATABASE.md §3 —
    normative text is never stored without this, by rule.
    """

    valid_from: Mapped[date] = mapped_column(nullable=False)
    valid_to: Mapped[date | None] = mapped_column(nullable=True)


def workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
