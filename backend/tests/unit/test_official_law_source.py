"""OfficialLawSource — Phase 5 defensive client tests (LEGAL-SOURCE-MATRIX.md
§1/§4). No live network call: httpx.MockTransport stands in for
publication.pravo.gov.ru so these tests exercise the parsing/failure logic
deterministically, without asserting anything about the real portal's
actual (still-unconfirmed) response shape.
"""
from __future__ import annotations

import httpx
import pytest

from app.sources.official.official_law_source import OfficialLawSource, SourceContractError, _parse_public_blocks


def test_parse_public_blocks_accepts_bare_list():
    payload = [{"id": "1", "title": "Раздел I"}, {"id": "2", "name": "Раздел II"}]
    assert _parse_public_blocks(payload, "http://x") == [("1", "Раздел I"), ("2", "Раздел II")]


def test_parse_public_blocks_accepts_envelope():
    payload = {"blocks": [{"BlockId": "3", "Name": "Раздел III"}]}
    assert _parse_public_blocks(payload, "http://x") == [("3", "Раздел III")]


def test_parse_public_blocks_rejects_unexpected_top_level_shape():
    with pytest.raises(SourceContractError):
        _parse_public_blocks("not a list or dict", "http://x")


def test_parse_public_blocks_rejects_item_missing_id_or_title():
    with pytest.raises(SourceContractError):
        _parse_public_blocks([{"title": "Раздел I"}], "http://x")  # missing id
    with pytest.raises(SourceContractError):
        _parse_public_blocks([{"id": "1"}], "http://x")  # missing title


@pytest.mark.asyncio
async def test_search_never_fabricates_result_on_malformed_response(monkeypatch):
    async def fake_get(self, url):
        return httpx.Response(200, json={"unexpected": "shape"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    source = OfficialLawSource(base_url="https://publication.pravo.gov.ru")
    from app.sources.base import SourceQuery

    with pytest.raises(SourceContractError):
        await source.search(SourceQuery(text="ГК РФ"))


@pytest.mark.asyncio
async def test_sync_reports_source_unavailable_never_raises(monkeypatch):
    async def fake_get(self, url):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    source = OfficialLawSource(base_url="https://publication.pravo.gov.ru")
    report = await source.sync()

    assert report.failed == 1
    assert "SOURCE_UNAVAILABLE" in report.note


@pytest.mark.asyncio
async def test_fetch_refuses_rather_than_guessing_document_contract():
    source = OfficialLawSource(base_url="https://publication.pravo.gov.ru")
    with pytest.raises(SourceContractError):
        await source.fetch("any-id")


@pytest.mark.asyncio
async def test_search_filters_well_formed_blocks_by_title(monkeypatch):
    async def fake_get(self, url):
        return httpx.Response(200, json=[{"id": "1", "title": "Гражданский кодекс РФ"}, {"id": "2", "title": "Налоговый кодекс РФ"}])

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    source = OfficialLawSource(base_url="https://publication.pravo.gov.ru")
    from app.sources.base import SourceQuery

    hits = await source.search(SourceQuery(text="гражданский"))
    assert len(hits) == 1
    assert hits[0].external_id == "1"
