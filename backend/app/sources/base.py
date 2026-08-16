"""LegalDataSource Protocol (LEGAL-SOURCES.md §2).

Ingestion/retrieval code depends only on this Protocol, never on a
source's concrete API shape — adding a new source is implement + register,
nothing else changes. No implementation of this Protocol may fabricate
content and present it as if it came from a real source (brief §7,
LEGAL-SOURCES.md §1) — mocks must be unambiguously labeled as mock data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class SourceQuery:
    text: str
    jurisdiction: str = "RU"
    filters: dict[str, Any] = field(default_factory=dict)
    limit: int = 20


@dataclass
class SourceHit:
    external_id: str
    title: str
    snippet: str
    url: str | None = None
    score: float | None = None


@dataclass
class RawDocument:
    external_id: str
    title: str
    content: str
    source_url: str | None = None
    published_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncReport:
    added: int = 0
    updated: int = 0
    failed: int = 0
    note: str = ""
    ran_at: datetime = field(default_factory=datetime.utcnow)


class LegalDataSource(Protocol):
    """One implementation per external legal data origin. See LEGAL-SOURCES.md §3."""

    source_name: str

    async def search(self, query: SourceQuery) -> list[SourceHit]: ...

    async def fetch(self, external_id: str) -> RawDocument: ...

    async def sync(self, since: datetime | None = None) -> SyncReport: ...
