from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_reports_database_check(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "database" in body["checks"]
    assert body["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_ready_reports_schema_check(client):
    """Staging audit §7 — /ready must also confirm migrations actually ran,
    not just that the database is reachable (a fresh, unmigrated Neon
    project would otherwise report ready while every query fails).
    """
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "schema" in body["checks"]


@pytest.mark.asyncio
async def test_ready_is_ok_once_schema_exists(client, db_session):
    # db_session pulls in the db_engine fixture, which provisions the full
    # schema via Base.metadata.create_all() — the same tables `alembic
    # upgrade head` would create, just via a different path (see main.py's
    # /ready docstring). Requesting it here is what makes "ok" a true
    # guarantee, unlike the looser checks above that don't require schema
    # to exist yet.
    response = await client.get("/ready")
    body = response.json()
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["schema"] == "ok"
    assert body["status"] == "ok"
