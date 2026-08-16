"""Async SQLAlchemy engine/session + Postgres RLS tenant-context helper.

Tenant isolation (LEGAL-SECURITY.md §2) is enforced two ways: repositories
scope every query by workspace_id explicitly, AND every request-scoped
session sets a Postgres session-local `app.current_workspace_id` GUC that
row-level-security policies on tenant tables key off of. This module owns
the second mechanism; app/repositories/* owns the first.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_database_url(url: str) -> str:
    """Neon (and most managed Postgres UIs) hand out connection strings with
    `?sslmode=require` — the libpq/psycopg convention. SQLAlchemy's asyncpg
    dialect reads SSL configuration from a query parameter named `ssl`, not
    `sslmode`; passed through unchanged, `sslmode` is silently ignored by
    asyncpg (staging audit §8). Rewriting the key here means a connection
    string copy-pasted from Neon's dashboard (with the driver prefix changed
    to `postgresql+asyncpg://`) works without the operator needing to know
    this detail. A no-op for any URL that doesn't set `sslmode`.
    """
    parsed = make_url(url)
    if "sslmode" not in parsed.query:
        return url
    query = dict(parsed.query)
    query["ssl"] = query.pop("sslmode")
    return str(parsed.set(query=query))


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — plain session, no tenant context set.

    Use `workspace_scoped_session` instead for any request that touches
    tenant data (see app/security/tenant.py).
    """
    async with get_session_factory()() as session:
        yield session


@asynccontextmanager
async def workspace_scoped_session(workspace_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    """Session with the RLS session-local workspace GUC set for its lifetime.

    Postgres RLS policies (see infra/postgres/rls.sql) reference
    current_setting('app.current_workspace_id', true) — this is where
    that value comes from. set_config's third arg (true) scopes it to the
    current transaction, so it never leaks across pooled connections.
    """
    async with get_session_factory()() as session:
        await session.execute(text("SELECT set_config('app.current_workspace_id', :wid, true)"), {"wid": str(workspace_id)})
        yield session
