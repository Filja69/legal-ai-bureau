"""_normalize_database_url — two independent PaaS/DB-dashboard connection
string quirks, both aimed at "the operator pasted the string exactly as
given, without knowing SQLAlchemy async-driver conventions":

1. Railway audit (production incident): Railway's (and Heroku's)
   auto-injected DATABASE_URL is a bare `postgresql://` or `postgres://`
   with no driver component. `create_async_engine()` resolves that to
   SQLAlchemy's classic *synchronous* default for the postgresql dialect,
   psycopg2 — never a dependency of this project — and fails with
   `ModuleNotFoundError: No module named 'psycopg2'` at engine construction
   time, reproduced byte-for-byte against the real Railway deployment
   error before this fix. psycopg2 was never actually required.
2. Staging audit §8: Neon hands out `?sslmode=require` (libpq/psycopg
   convention); asyncpg's dialect reads `ssl`, not `sslmode`.

Both paths are also regression-tested for NOT masking the real password —
`str(URL)` (as opposed to `render_as_string(hide_password=False)`) silently
replaces any password with the literal string `***`, which would have
broken every real connection this function actually rewrites while looking
correct in casual testing (see the docstring in app/db/session.py).
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.session import _normalize_database_url

# --- Railway/Heroku: bare scheme -> +asyncpg (the reported production bug) ---


def test_normalize_rewrites_bare_postgresql_scheme_to_asyncpg():
    """Exact shape of Railway's auto-injected DATABASE_URL."""
    url = "postgresql://user:pass@railway-host.proxy.rlwy.net:12345/railway"
    result = _normalize_database_url(url)
    assert result.startswith("postgresql+asyncpg://")


def test_normalize_rewrites_postgres_scheme_to_asyncpg():
    """Heroku's older short scheme — SQLAlchemy doesn't even recognize
    "postgres" as a dialect name at all (NoSuchModuleError), a harder
    failure than the psycopg2 ModuleNotFoundError from bare "postgresql".
    """
    url = "postgres://user:pass@railway-host.proxy.rlwy.net:12345/railway"
    result = _normalize_database_url(url)
    assert result.startswith("postgresql+asyncpg://")


def test_normalized_railway_url_actually_constructs_an_asyncpg_engine():
    """The real regression test: this exact failure mode — engine
    construction raising ModuleNotFoundError('psycopg2') — reproduced
    against the unmodified URL before this fix; must not raise after it,
    and must resolve to the asyncpg driver, not psycopg2.
    """
    url = "postgresql://user:pass@railway-host.proxy.rlwy.net:12345/railway"
    engine = create_async_engine(_normalize_database_url(url), pool_pre_ping=True, future=True)
    assert engine.dialect.driver == "asyncpg"


def test_unmodified_bare_postgresql_url_reproduces_the_reported_psycopg2_error():
    """Documents the actual root cause: without normalization, engine
    construction fails trying to import psycopg2 — not a connectivity
    problem, not a missing table, purely a driver-resolution default.
    """
    url = "postgresql://user:pass@railway-host.proxy.rlwy.net:12345/railway"
    with pytest.raises(ModuleNotFoundError, match="psycopg2"):
        create_async_engine(url, pool_pre_ping=True, future=True)


# --- Neon: sslmode -> ssl ---


def test_normalize_rewrites_sslmode_to_ssl():
    url = "postgresql+asyncpg://user:pass@ep-example.neon.tech/dbname?sslmode=require"
    result = _normalize_database_url(url)
    assert "ssl=require" in result
    assert "sslmode" not in result


def test_normalize_preserves_other_query_params():
    url = "postgresql+asyncpg://user:pass@ep-example.neon.tech/dbname?sslmode=require&application_name=legal-ai-bureau"
    result = _normalize_database_url(url)
    assert "ssl=require" in result
    assert "application_name=legal-ai-bureau" in result
    assert "sslmode" not in result


# --- No-op cases ---


def test_normalize_is_a_noop_without_sslmode_or_bare_scheme():
    url = "postgresql+asyncpg://legal:legal@localhost:5437/legal_ai_bureau"
    assert _normalize_database_url(url) == url


# --- Password preservation (the masking regression found while fixing the Railway bug) ---


def test_normalize_preserves_the_real_password_never_the_masked_str_form():
    """str(URL) masks any password as the literal string '***' — a
    display-safety default, not something safe to feed to a real
    connection. Both rewrite paths must use render_as_string(hide_password=False).
    """
    railway_url = "postgresql://admin:S3cr3tPassw0rd123@railway-host.proxy.rlwy.net:12345/railway"
    result = _normalize_database_url(railway_url)
    assert "***" not in result
    assert "S3cr3tPassw0rd123" in result


def test_normalize_preserves_real_password_on_sslmode_rewrite_path():
    neon_url = "postgresql+asyncpg://user:CorrectHorseBattery9@ep-example.neon.tech/dbname?sslmode=require"
    result = _normalize_database_url(neon_url)
    assert "***" not in result
    assert "CorrectHorseBattery9" in result
