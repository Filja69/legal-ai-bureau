"""TaxSource — ФНС open data (Единый реестр юрлиц/ИП, public tax signals).
LEGAL-SOURCES.md §3. Scaffold stage — see OfficialLawSource for the pattern.
"""
from __future__ import annotations

from datetime import datetime

from app.sources.base import RawDocument, SourceHit, SourceQuery, SyncReport


class TaxSource:
    source_name = "fns_open_data"

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def search(self, query: SourceQuery) -> list[SourceHit]:
        # TODO(Phase 5, Due Diligence): implement against ФНС open-data endpoints.
        raise NotImplementedError(f"{self.source_name}.search is not implemented yet — see LEGAL-SOURCES.md §3.")

    async def fetch(self, external_id: str) -> RawDocument:
        raise NotImplementedError(f"{self.source_name}.fetch is not implemented yet — see LEGAL-SOURCES.md §3.")

    async def sync(self, since: datetime | None = None) -> SyncReport:
        raise NotImplementedError(f"{self.source_name}.sync is not implemented yet — see LEGAL-SOURCES.md §3.")
