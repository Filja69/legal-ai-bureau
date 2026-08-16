"""MockLegalDataSource — serves the deterministic dataset in
app/sources/mock/dataset.py (brief §13, Phase 2).

Used for local dev/tests and as the current stand-in for
CommercialLegalDBSource (КонсультантПлюс/ГАРАНТ) until a licensing
agreement is signed (LEGAL-SOURCES.md §4). Every hit/document it returns
carries `metadata["is_mock"] = True` so it can never be mistaken for a
verified real-world source downstream (e.g. by the Citation Validator,
LEGAL-RAG.md §4) — enforced end-to-end through ingestion into
LegalSource.is_mock / EmbeddingChunk.is_mock / CitationCheck's MOCK status.
"""
from __future__ import annotations

import json
from datetime import datetime

from app.sources.base import RawDocument, SourceHit, SourceQuery, SyncReport
from app.sources.mock.dataset import MOCK_DATASET

_BY_EXTERNAL_ID = {record["external_id"]: record for record in MOCK_DATASET}


class MockLegalDataSource:
    source_name = "mock"

    async def search(self, query: SourceQuery) -> list[SourceHit]:
        text = (query.text or "").strip().lower()
        if not text:
            # Empty query = "discover everything" — used by the ingestion
            # pipeline's discover step (LEGAL-SOURCES.md §2 lifecycle).
            matches = MOCK_DATASET
        else:
            matches = [
                r for r in MOCK_DATASET
                if text in r["title"].lower()
                or text in r.get("text", "").lower()
                or text in r.get("legal_reasoning", "").lower()
                or text in r.get("claim_summary", "").lower()
            ]
        return [
            SourceHit(
                external_id=r["external_id"],
                title=f"[MOCK] {r['title']}",
                snippet=(r.get("text") or r.get("claim_summary") or "")[:200],
                url=None,
                score=1.0,
            )
            for r in matches[: query.limit]
        ]

    async def fetch(self, external_id: str) -> RawDocument:
        record = _BY_EXTERNAL_ID.get(external_id)
        if record is None:
            raise KeyError(f"No mock document with external_id={external_id!r}")
        return RawDocument(
            external_id=external_id,
            title=record["title"],
            content=json.dumps(record, ensure_ascii=False),
            source_url=None,
            published_at=record.get("publication_date"),
            metadata={"is_mock": True, "kind": record["kind"]},
        )

    async def sync(self, since: datetime | None = None) -> SyncReport:
        return SyncReport(added=len(MOCK_DATASET), updated=0, failed=0, note="mock source — deterministic fixture dataset")
