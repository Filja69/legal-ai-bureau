"""Generic ingestion framework interfaces (LEGAL-SOURCES.md §11-12, brief §11-12).

```
LegalSource -> SourceFetcher -> SourceParser -> SourceNormalizer -> SourceValidator -> Persistence -> Indexer
```

Nothing about a specific source is baked into `IngestionPipeline` (app/domains/
legal_knowledge/ingestion/pipeline.py) — a new source is: implement
`LegalDataSource` (app/sources/base.py) for fetch/search/sync, plus a
`SourceParser` that knows that source's raw format. The pipeline itself
never changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from app.sources.base import RawDocument

ParsedContentKind = Literal["law_article", "court_decision"]


@dataclass
class ParsedLegalContent:
    """Structured output of parsing a source's raw content — one record per
    norm-bearing unit (an article/clause redaction) or one court decision.
    Deliberately flat rather than a class hierarchy: at this scale a few
    unused fields per `kind` is cheaper to read than three dataclasses plus
    a discriminated union.
    """

    kind: ParsedContentKind
    title: str
    jurisdiction: str = "RU"
    publication_date: date | None = None
    effective_date: date | None = None

    # law_article fields
    law_short_name: str | None = None
    law_full_name: str | None = None
    code_type: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    text: str = ""
    hierarchy_path: list[str] = field(default_factory=list)
    valid_from: date | None = None
    valid_to: date | None = None
    amending_act_title: str | None = None
    amending_act_source_url: str | None = None

    # court_decision fields
    court_name: str | None = None
    court_level: str | None = None
    case_number: str | None = None
    decision_date: date | None = None
    parties: dict = field(default_factory=dict)
    claim_summary: str | None = None
    decision_summary: str | None = None
    legal_reasoning: str | None = None
    outcome: str | None = None


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


class SourceFetcher(Protocol):
    """Thin wrapper over LegalDataSource.fetch — kept as its own interface so a
    pipeline stage can be swapped/mocked independently of the source itself.
    """

    async def fetch(self, external_id: str) -> RawDocument: ...


class SourceParser(Protocol):
    """Turns a source's raw payload into structured ParsedLegalContent.
    One implementation per source *format*, not per source instance — e.g.
    a single parser could serve any source that happens to emit the same
    XML schema.
    """

    def parse(self, raw: RawDocument) -> ParsedLegalContent: ...


class SourceNormalizer(Protocol):
    """Encoding/whitespace/heading/date normalization (brief §6) — operates
    on the already-parsed structure, not raw text, so it never has to
    re-derive structure the parser already extracted.
    """

    def normalize(self, parsed: ParsedLegalContent) -> ParsedLegalContent: ...


class SourceValidator(Protocol):
    def validate(self, parsed: ParsedLegalContent) -> ValidationResult: ...


class LegalIndexer(Protocol):
    """Final ingestion-pipeline stage — implemented in app/rag/indexing (Phase 2
    §21-23) so `IngestionPipeline` doesn't need to know embeddings exist, only
    that "indexing" is a thing that happens to a persisted chunk.
    """

    async def index_chunk(self, chunk_type: str, chunk_id, text: str, metadata: dict) -> None: ...
