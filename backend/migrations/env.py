from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config.settings import get_settings
from app.db.session import _normalize_database_url
from app.models import Base  # noqa: F401 — registers all model metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Same URL normalization as app.db.session.get_engine() (staging audit §8,
# Railway psycopg2 incident) — migrations run through their own engine, not
# get_engine(), so this needs applying here too. Without it, `alembic
# upgrade head` against a bare postgresql:// DATABASE_URL (Railway/Heroku's
# auto-injected form) would fail trying to import psycopg2 exactly like the
# app's own /ready check did, and against Neon would silently ignore the
# sslmode query parameter.
config.set_main_option("sqlalchemy.url", _normalize_database_url(get_settings().database_url))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
