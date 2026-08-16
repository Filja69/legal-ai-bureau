"""CourtSource — public arbitration/general-jurisdiction court decision cards
(LEGAL-SOURCES.md §3). Scaffold stage — see OfficialLawSource for the pattern
this follows: real Protocol shape, real base_url wiring, no fabricated results.
"""
from __future__ import annotations

from datetime import datetime

from app.sources.base import RawDocument, SourceHit, SourceQuery, SyncReport


class CourtSource:
    source_name = "court_public_records"

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def search(self, query: SourceQuery) -> list[SourceHit]:
        # TODO(Phase 2): implement against kad.arbitr.ru / public court card index.
        raise NotImplementedError(f"{self.source_name}.search is not implemented yet — see LEGAL-SOURCES.md §3.")

    async def fetch(self, external_id: str) -> RawDocument:
        raise NotImplementedError(f"{self.source_name}.fetch is not implemented yet — see LEGAL-SOURCES.md §3.")

    async def sync(self, since: datetime | None = None) -> SyncReport:
        raise NotImplementedError(f"{self.source_name}.sync is not implemented yet — see LEGAL-SOURCES.md §3.")
