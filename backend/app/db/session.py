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
    """Two independent normalizations, both aimed at "the operator pasted a
    connection string exactly as their PaaS/DB dashboard gave it, without
    knowing SQLAlchemy async-driver conventions":

    1. Bare `postgresql://` or `postgres://` (no driver component) — this is
       exactly what Railway's and Heroku's auto-injected `DATABASE_URL`
       reference variables look like (e.g. `${{Postgres.DATABASE_URL}}` on
       Railway). `create_async_engine()` resolves an unspecified driver to
       SQLAlchemy's classic *synchronous* default for the "postgresql"
       dialect, psycopg2 — a package this project has never depended on
       (asyncpg is the only Postgres driver anywhere in this codebase) —
       and fails with `ModuleNotFoundError: No module named 'psycopg2'` the
       moment the engine is constructed. `postgres://` (Heroku's older
       short form) fails even harder: SQLAlchemy doesn't recognize
       "postgres" as a dialect name at all
       (`NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:postgres`).
       Reproduced empirically for both forms before writing this fix — see
       tests/unit/test_db_session_url_normalization.py. psycopg2 was never
       actually required; this was purely a URL-scheme default.
    2. Neon (and most managed Postgres UIs) hand out connection strings with
       `?sslmode=require` — the libpq/psycopg convention. SQLAlchemy's
       asyncpg dialect reads SSL configuration from a query parameter named
       `ssl`, not `sslmode`; passed through unchanged, `sslmode` is silently
       ignored by asyncpg (staging audit §8).

    A no-op (returns the original string unchanged) when neither applies.

    IMPORTANT: reserializes via `render_as_string(hide_password=False)`,
    never bare `str(url)` — SQLAlchemy's `URL.__str__` masks the password
    as the literal string `***` (a display-safety default so a URL doesn't
    leak into logs/tracebacks unmasked), which would silently replace the
    real password with three literal asterisks in the connection string
    actually handed to asyncpg the moment this function changes anything.
    Caught in testing before this ever reached a real deployment — see
    test_normalize_preserves_the_real_password_never_the_masked_str_form.
    """
    parsed = make_url(url)
    changed = False

    if parsed.drivername in ("postgresql", "postgres"):
        parsed = parsed.set(drivername="postgresql+asyncpg")
        changed = True

    if "sslmode" in parsed.query:
        query = dict(parsed.query)
        query["ssl"] = query.pop("sslmode")
        parsed = parsed.set(query=query)
        changed = True

    return parsed.render_as_string(hide_password=False) if changed else url


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
