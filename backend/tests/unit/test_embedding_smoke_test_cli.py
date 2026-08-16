"""app.cli.embedding_smoke_test — Phase 6.5 brief §4. All offline: no real
API key is available in CI, so these tests verify the CLI's own control
flow (never a silent mock fallback) rather than a live OpenAI response.
"""
from __future__ import annotations

import pytest

from app.cli import embedding_smoke_test
from app.config.settings import Settings


@pytest.mark.asyncio
async def test_smoke_test_reports_missing_provider_config(monkeypatch, capsys):
    monkeypatch.setattr(embedding_smoke_test, "get_settings", lambda: Settings(embedding_provider="mock"))
    exit_code = await embedding_smoke_test.main()
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "REAL API TEST NOT RUN" in out
    assert "not 'openai'" in out


@pytest.mark.asyncio
async def test_smoke_test_reports_missing_api_key(monkeypatch, capsys):
    monkeypatch.setattr(
        embedding_smoke_test, "get_settings", lambda: Settings(embedding_provider="openai", openai_api_key=None)
    )
    exit_code = await embedding_smoke_test.main()
    out = capsys.readouterr().out
    assert exit_code == 1
    assert "OPENAI_API_KEY missing" in out
    assert "REAL API TEST NOT RUN" in out


def test_smoke_test_never_imports_the_indexer():
    """Even on a successful embed, the CLI must never touch EmbeddingChunk —
    verified by asserting LegalChunkIndexer is never bound as a name in this
    module (i.e. never imported/constructed), not just absent from prose."""
    assert not hasattr(embedding_smoke_test, "LegalChunkIndexer")
    assert not hasattr(embedding_smoke_test, "IngestionPipeline")
