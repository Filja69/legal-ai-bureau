"""OfficialLawSource — publication.pravo.gov.ru (LEGAL-SOURCE-MATRIX.md §1).

Phase 5 status: a real HTTP client against the documented endpoints
(`/api/PublicBlocks/`, `/api/Categories`) — not a scaffold anymore. But it
has **not been exercised against a live response** this session: every
attempt to reach pravo.gov.ru from this environment failed at the socket
level (see LEGAL-SOURCE-MATRIX.md §4). The exact response schema below is
reconstructed from search-result snippets of the portal's own documentation,
not a confirmed live payload.

Consequently this client is defensive by construction: it never invents a
result on an unexpected response shape. A shape it doesn't recognize raises
`SourceContractError` rather than being silently coerced into something
that looks like a valid `SourceHit`/`RawDocument` — per the hard rule that a
source being unavailable/unconfirmed must surface as SOURCE_UNAVAILABLE,
never quietly degrade to empty-but-successful or (worse) fabricated data.
The first real call against a live endpoint is the actual contract
confirmation step; this code is written to fail loudly the moment reality
diverges from what's documented here, so that confirmation is unambiguous.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.sources.base import RawDocument, SourceHit, SourceQuery, SyncReport


class SourceContractError(RuntimeError):
    """Raised when a source's real response doesn't match its documented shape.

    Never caught and papered over with an empty/mock result — the caller
    must see this as SOURCE_UNAVAILABLE (brief §70), not as "zero results."
    """


class OfficialLawSource:
    source_name = "official_law_pravo_gov_ru"

    def __init__(self, base_url: str, timeout_seconds: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def search(self, query: SourceQuery) -> list[SourceHit]:
        blocks = await self._get_public_blocks()
        # publication.pravo.gov.ru's search surface is block/category
        # enumeration, not a free-text query endpoint per the documentation
        # found — so "search" here means "filter the known block list by
        # query text against block titles," which is honest about what this
        # endpoint can actually do until the real full-text search contract
        # is confirmed live.
        query_lower = query.text.lower()
        hits = [
            SourceHit(
                external_id=str(block_id), title=title,
                snippet=title, url=f"{self._base_url}/documents/block/{block_id}", score=None,
            )
            for block_id, title in blocks
            if query_lower in title.lower()
        ]
        return hits[: query.limit]

    async def fetch(self, external_id: str) -> RawDocument:
        # Document-text retrieval contract was not confirmed live this
        # session (LEGAL-SOURCE-MATRIX.md §1/§4) — implementing this against
        # a guessed endpoint/response shape would risk silently parsing
        # garbage as a legal document. Refuses explicitly instead.
        raise SourceContractError(
            f"{self.source_name}.fetch: document-text retrieval contract unconfirmed — "
            "see LEGAL-SOURCE-MATRIX.md §1/§4. Requires a live response before implementation."
        )

    async def sync(self, since: datetime | None = None) -> SyncReport:
        try:
            blocks = await self._get_public_blocks()
        except SourceContractError as exc:
            return SyncReport(added=0, updated=0, failed=1, note=f"SOURCE_UNAVAILABLE: {exc}")
        return SyncReport(added=0, updated=0, failed=0, note=f"discovered {len(blocks)} publication blocks; fetch() not yet implemented")

    async def _get_public_blocks(self) -> list[tuple[str, str]]:
        url = f"{self._base_url}/api/PublicBlocks/"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise SourceContractError(f"{self.source_name}: request to {url} failed: {exc}") from exc

        if response.status_code != 200:
            raise SourceContractError(f"{self.source_name}: {url} returned HTTP {response.status_code}")

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise SourceContractError(f"{self.source_name}: {url} did not return valid JSON") from exc

        return _parse_public_blocks(payload, url)


def _parse_public_blocks(payload: Any, url: str) -> list[tuple[str, str]]:
    """Defensive parse — accepts a bare list or a `{"blocks": [...]}` envelope
    (both are plausible for a portal-defined JSON API per the documentation
    found), and requires each item to carry an id-like and title-like field
    under one of a few plausible names. Anything else raises rather than
    silently returning an empty/partial list.
    """
    items = payload if isinstance(payload, list) else payload.get("blocks") if isinstance(payload, dict) else None
    if items is None:
        raise SourceContractError(f"official_law_pravo_gov_ru: unexpected response shape from {url}: {type(payload).__name__}")

    blocks: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise SourceContractError(f"official_law_pravo_gov_ru: unexpected block item shape from {url}: {item!r}")
        block_id = item.get("id") or item.get("blockId") or item.get("BlockId")
        title = item.get("title") or item.get("name") or item.get("Name")
        if block_id is None or title is None:
            raise SourceContractError(f"official_law_pravo_gov_ru: block item missing id/title from {url}: {item!r}")
        blocks.append((str(block_id), str(title)))
    return blocks
