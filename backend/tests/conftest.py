from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    # asyncpg's connection cleanup schedules a task on close(); Windows'
    # default ProactorEventLoop tears itself down in a way that races with
    # that task across pytest-asyncio's per-test event loops. The Selector
    # policy doesn't have this failure mode. Windows-only, dev/test-only —
    # never touches how the app runs in production (Linux containers).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://legal:legal@localhost:5437/legal_ai_bureau_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6391/1")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("LLM_PROVIDER", "mock")
# Phase 7 brief §7: the dev/no-token bypass requires an EXPLICIT opt-in —
# this is that explicit opt-in, scoped to the test suite only. Tests that
# exercise real JWT/membership enforcement (tests/security/test_auth*.py)
# override ENVIRONMENT/AUTH_DEV_MODE per-test via monkeypatch, not here.
os.environ.setdefault("AUTH_DEV_MODE", "true")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.db.session as db_session_module
from app.db.base import Base
from app.db.session import get_engine
from app.main import create_app


@pytest.fixture(autouse=True)
async def _reset_db_engine_after_each_test():
    """Any test can indirectly create the cached engine singleton (e.g. hitting
    /ready, which opens a connection to check DB health) without going through
    the db_engine fixture. Left alive, that pooled connection is invalid once
    pytest-asyncio hands the next test a new event loop. Disposing + clearing
    the singleton after every test (not just DB-fixture tests) closes that gap.
    """
    yield
    if db_session_module._engine is not None:
        await db_session_module._engine.dispose()
        db_session_module._engine = None
        db_session_module._session_factory = None


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_engine():
    """Requires a real Postgres reachable at DATABASE_URL (docker-compose postgres
    service). Creates the full schema, yields, drops it — tests never share state.

    Disposes the engine's connection pool before returning, and resets the
    module-level singleton: pytest-asyncio gives each test function its own
    event loop, but app.db.session.get_engine() caches a single AsyncEngine
    for the process. A pooled asyncpg connection opened under test N's loop
    is invalid under test N+1's loop ("Event loop is closed" during cleanup);
    disposing isn't always enough to prevent a pending cancellation task from
    outliving the loop, so the fixture also drops the cached engine entirely,
    forcing get_engine() to build a fresh one (and pool) next test.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        # The test DB is a plain `CREATE DATABASE` sibling, not the container's
        # primary POSTGRES_DB — infra/postgres/init.sql only runs against the
        # latter on first container boot, so these extensions must be ensured
        # here too (migrations/versions/0001_initial_schema.py does the same
        # for the real, Alembic-tracked database).
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    db_session_module._engine = None
    db_session_module._session_factory = None


@pytest.fixture
async def db_session(db_engine):
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
