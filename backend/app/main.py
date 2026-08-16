"""FastAPI application factory — Legal AI Bureau backend entrypoint."""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_router
from app.config.settings import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_engine

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", environment=get_settings().environment)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.assert_production_safe()

    app = FastAPI(title="Legal AI Bureau API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        # Cheap and available pre-auth (staging audit §20 — "workspace
        # identifiers where appropriate"): read the header directly rather
        # than re-running JWT/membership verification here, which stays the
        # dependencies' job. Absent for unauthenticated routes (login, health).
        workspace_id = request.headers.get("X-Workspace-Id")
        start = time.perf_counter()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, **({"workspace_id": workspace_id} if workspace_id else {}))
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-Id"] = request_id
        route = request.scope.get("route")
        logger.info(
            "request_completed",
            path=request.url.path,
            route=route.path if route is not None else None,
            method=request.method,
            status_code=response.status_code,
            latency_ms=round(latency_ms, 2),
        )
        return response

    app.include_router(api_router, prefix="/api/v1/legal")

    @app.get("/health", tags=["system"])
    async def health() -> dict:
        """Liveness — process is up. Must never touch the database."""
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def ready() -> dict:
        """Readiness — dependencies AND schema are actually usable.

        Staging audit §7: DB connectivity alone isn't enough — a freshly
        provisioned, unmigrated database (e.g. a brand new Neon project)
        would answer `SELECT 1` fine while every application query fails.
        Querying a core, always-present table confirms the schema exists
        without hardcoding an Alembic revision id (so this doesn't need
        editing on every migration) and without assuming migrations were
        applied via `alembic upgrade head` specifically — the test suite's
        `db_engine` fixture provisions the same tables via
        `Base.metadata.create_all()` directly, which this check is equally
        satisfied by.

        Redis/document storage are deliberately NOT checked here (staging
        audit §6): Redis has zero functional usage anywhere in this
        codebase today, and document storage failures surface per-request
        on upload/download, not as a global readiness gate.
        """
        checks: dict[str, str] = {}
        try:
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
                checks["database"] = "ok"
                await conn.execute(text("SELECT 1 FROM workspaces LIMIT 1"))
                checks["schema"] = "ok"
        except Exception as exc:  # pragma: no cover - exercised via integration test
            checks.setdefault("database", f"error: {exc}")
            checks.setdefault("schema", f"error: {exc}")

        overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
        return {"status": overall, "checks": checks}

    return app


app = create_app()
