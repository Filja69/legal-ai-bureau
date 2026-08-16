"""Staging audit §8 — Neon (and most managed Postgres dashboards) hand out
connection strings with `?sslmode=require`, the libpq/psycopg convention.
SQLAlchemy's asyncpg dialect reads SSL config from `ssl`, not `sslmode` —
`_normalize_database_url` rewrites the key so a copy-pasted Neon URL (with
the driver prefix changed to `postgresql+asyncpg://`) works unmodified.
"""
from __future__ import annotations

from app.db.session import _normalize_database_url


def test_normalize_rewrites_sslmode_to_ssl():
    url = "postgresql+asyncpg://user:pass@ep-example.neon.tech/dbname?sslmode=require"
    result = _normalize_database_url(url)
    assert "ssl=require" in result
    assert "sslmode" not in result


def test_normalize_is_a_noop_without_sslmode():
    url = "postgresql+asyncpg://legal:legal@localhost:5437/legal_ai_bureau"
    assert _normalize_database_url(url) == url


def test_normalize_preserves_other_query_params():
    url = "postgresql+asyncpg://user:pass@ep-example.neon.tech/dbname?sslmode=require&application_name=legal-ai-bureau"
    result = _normalize_database_url(url)
    assert "ssl=require" in result
    assert "application_name=legal-ai-bureau" in result
    assert "sslmode" not in result
