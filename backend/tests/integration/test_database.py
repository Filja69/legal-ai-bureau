from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_database_connection(db_engine):
    async with db_engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_all_models_create_tables(db_engine):
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        )
        tables = {row[0] for row in result}
    for expected in ("organizations", "workspaces", "users", "cases", "documents", "legal_documents", "citations", "audit_logs"):
        assert expected in tables
