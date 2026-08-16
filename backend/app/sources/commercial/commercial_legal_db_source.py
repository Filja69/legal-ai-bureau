"""CommercialLegalDBSource — КонсультантПлюс / ГАРАНТ adapter.

Real implementation is blocked on a signed licensing agreement
(LEGAL-SOURCES.md §1, §4). This class exists purely as the typed seam a
real client drops into later; today it defers entirely to
MockLegalDataSource rather than talking to any commercial endpoint.
"""
from __future__ import annotations

from datetime import datetime

from app.sources.base import RawDocument, SourceHit, SourceQuery, SyncReport
from app.sources.mock.mock_source import MockLegalDataSource


class CommercialLegalDBSource:
    source_name = "commercial_legal_db"

    def __init__(self, licensed: bool = False) -> None:
        self._licensed = licensed
        self._mock = MockLegalDataSource()

    async def search(self, query: SourceQuery) -> list[SourceHit]:
        if not self._licensed:
            # TODO: replace with a real КонсультантПлюс/ГАРАНТ API client once a
            # licensing agreement is signed. Falls back to mock fixtures so
            # ingestion/retrieval/UI can be built and tested now.
            return await self._mock.search(query)
        raise NotImplementedError("Licensed commercial DB client not yet implemented.")

    async def fetch(self, external_id: str) -> RawDocument:
        if not self._licensed:
            return await self._mock.fetch(external_id)
        raise NotImplementedError("Licensed commercial DB client not yet implemented.")

    async def sync(self, since: datetime | None = None) -> SyncReport:
        if not self._licensed:
            return await self._mock.sync(since)
        raise NotImplementedError("Licensed commercial DB client not yet implemented.")
