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


# --- Railway psycopg2 incident regression (see app/db/session.py) ---


@pytest.mark.asyncio
async def test_ready_never_reports_psycopg2_for_a_bare_postgresql_url(client, monkeypatch):
    """The exact production bug: Railway's auto-injected DATABASE_URL is a
    bare `postgresql://` with no driver. Before the fix, /ready's database
    AND schema checks both failed with "No module named 'psycopg2'" — a
    driver-resolution artifact, not a real connectivity problem. This
    reproduces that URL shape end-to-end through the real HTTP endpoint and
    asserts psycopg2 never appears in the response; whatever real error
    surfaces instead (DNS failure, refused connection) is legitimate.
    """
    import app.db.session as db_session_module
    from app.config.settings import Settings

    railway_shaped_settings = Settings(
        database_url="postgresql://user:pass@nonexistent-railway-host.invalid:12345/railway"
    )
    monkeypatch.setattr(db_session_module, "get_settings", lambda: railway_shaped_settings)

    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"  # genuinely unreachable — must not be faked as "ok"
    assert "psycopg2" not in body["checks"]["database"]
    assert "psycopg2" not in body["checks"]["schema"]


@pytest.mark.asyncio
async def test_ready_reports_degraded_honestly_for_an_unreachable_but_correctly_formed_database(client, monkeypatch):
    """Isolates "database is down" from "driver resolution failed" — even
    with the correct postgresql+asyncpg:// scheme, an unreachable host must
    still produce a real, non-fabricated "degraded" response.
    """
    import app.db.session as db_session_module
    from app.config.settings import Settings

    unreachable_settings = Settings(database_url="postgresql+asyncpg://user:pass@nonexistent-host.invalid:5432/db")
    monkeypatch.setattr(db_session_module, "get_settings", lambda: unreachable_settings)

    response = await client.get("/ready")
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] != "ok"
    assert body["checks"]["schema"] != "ok"


@pytest.mark.asyncio
async def test_ready_url_normalization_applies_regardless_of_environment(client, monkeypatch):
    """The Railway URL fix must not be accidentally gated behind
    ENVIRONMENT — get_engine() normalizes unconditionally, for every
    environment, since a malformed driver scheme is never intentional.
    """
    import app.db.session as db_session_module
    from app.config.settings import Settings

    for environment in ("development", "staging", "production"):
        db_session_module._engine = None
        db_session_module._session_factory = None
        settings = Settings(
            environment=environment,
            jwt_secret="a-real-random-secret-value",
            database_url="postgresql://user:pass@nonexistent-railway-host.invalid:12345/railway",
        )
        monkeypatch.setattr(db_session_module, "get_settings", lambda s=settings: s)

        response = await client.get("/ready")
        body = response.json()
        assert "psycopg2" not in body["checks"]["database"], f"psycopg2 leaked through for environment={environment!r}"
