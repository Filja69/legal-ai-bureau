from __future__ import annotations

import pytest

from app.sources.base import SourceQuery
from app.sources.mock.dataset import MOCK_COURT_DECISIONS, MOCK_LAW_ARTICLES
from app.sources.mock.mock_source import MockLegalDataSource


@pytest.mark.asyncio
async def test_mock_source_search_matches_deterministic_dataset():
    source = MockLegalDataSource()
    hits = await source.search(SourceQuery(text="309"))
    assert len(hits) >= 1
    assert all("[MOCK]" in h.title for h in hits)
    assert any("309" in h.title for h in hits)


@pytest.mark.asyncio
async def test_mock_source_empty_query_discovers_everything():
    source = MockLegalDataSource()
    hits = await source.search(SourceQuery(text="", limit=100))
    assert len(hits) == len(MOCK_LAW_ARTICLES) + len(MOCK_COURT_DECISIONS)


@pytest.mark.asyncio
async def test_mock_source_fetch_marks_metadata_is_mock():
    source = MockLegalDataSource()
    document = await source.fetch("mock-gk-309-v1")
    assert document.metadata["is_mock"] is True
    assert document.metadata["kind"] == "law_article"


@pytest.mark.asyncio
async def test_mock_source_fetch_unknown_id_raises():
    source = MockLegalDataSource()
    with pytest.raises(KeyError):
        await source.fetch("does-not-exist")


@pytest.mark.asyncio
async def test_mock_source_sync_reports_full_dataset_size():
    source = MockLegalDataSource()
    report = await source.sync()
    assert report.added == len(MOCK_LAW_ARTICLES) + len(MOCK_COURT_DECISIONS)
    assert "mock" in report.note.lower()


@pytest.mark.asyncio
async def test_official_law_source_does_not_fabricate_results(monkeypatch):
    """Real-source adapters must fail loudly, never return fabricated data
    pretending to come from a government source (LEGAL-SOURCES.md §1).

    No live network call here on purpose (brief §57/§64) — a malformed
    response is simulated via httpx.AsyncClient.get so this stays a fast,
    deterministic unit test regardless of whether pravo.gov.ru is reachable
    from wherever CI runs. See tests/unit/test_official_law_source.py for
    the full defensive-parsing test suite this one is a subset of.
    """
    import httpx

    from app.sources.official.official_law_source import OfficialLawSource, SourceContractError

    async def fake_get(self, url):
        return httpx.Response(200, json={"unexpected": "shape"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    source = OfficialLawSource(base_url="https://pravo.gov.ru")
    with pytest.raises(SourceContractError):
        await source.search(SourceQuery(text="anything"))
