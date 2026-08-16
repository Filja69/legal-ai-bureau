# LEGAL AI BUREAU — Legal Data Source Connector Architecture

## 1. Hard constraints (brief §4, §70 — non-negotiable)

- No paywall bypass. No breaking access protections. No unlicensed scraping of closed databases (КонсультантПлюс, ГАРАНТ, ГАС «Правосудие» beyond what's publicly published).
- No storing/indexing content whose license forbids retention — the `Source.license_type` field gates ingestion, checked before, not after, storing content.
- Connect only via: official public APIs/publications, licensed commercial feeds, or user-supplied documents/exports.

## 2. Connector interface

```python
class LegalDataSource(Protocol):
    source: Source  # metadata row — id, license_type, jurisdiction

    async def search(self, query: SourceQuery) -> list[SourceHit]: ...
    async def fetch(self, external_id: str) -> RawDocument: ...
    async def sync(self, since: datetime | None = None) -> SyncReport: ...
```

Business logic (ingestion pipeline, chunking, embedding, indexing) depends only on this Protocol — never on a specific source's API shape. Adding a new source is: implement the Protocol, register it, no changes elsewhere.

## 3. Implementations (v1 — RU jurisdiction)

| Class | Target | v1 status |
|---|---|---|
| `OfficialLawSource` | pravo.gov.ru (Официальный интернет-портал правовой информации) — federal laws, codes, presidential/government acts | Real connector: public, no license required for published legal acts |
| `CourtSource` | Published decisions of arbitration courts (kad.arbitr.ru public card index) and general jurisdiction courts where public | Real connector for public case cards; full-text where publicly posted |
| `TaxSource` | ФНС open data (Единый реестр юрлиц/ИП, налоговая задолженность where public) | Real connector against published open-data endpoints |
| `RegistrySource` | Росреестр public lookups (where API/open data exists) | Real connector, scoped to public-data endpoints only |
| `CommercialLegalDBSource` | КонсультантПлюс / ГАРАНТ | **Mock implementation + TODO** — requires a signed licensing agreement before going live; interface fully implemented against the Protocol so switching in a real feed later is a config change, not a rewrite |
| `UserDocumentSource` | User-uploaded contracts, scans, exports from commercial DBs the user is separately licensed for | Real connector — feeds the Document Ingestion pipeline, never merges into the shared public KB (tenant-isolated) |

Each real connector still respects `sync_strategy` (`api` vs `feed` vs `manual`) and records `SyncReport` (documents added/updated/failed) surfaced in the Admin Panel ([LEGAL-API.md](LEGAL-API.md) `/admin`).

## 4. Mock implementation pattern (brief §73 — don't block development on missing external APIs)

```python
class CommercialLegalDBSource:
    """TODO: replace with real КонсультантПлюс/ГАРАНТ API client once
    a licensing agreement is signed. Mock returns a fixed small fixture
    set so ingestion pipeline, retrieval, and UI can be built/tested now."""

    async def search(self, query: SourceQuery) -> list[SourceHit]:
        return _load_fixture_hits(query)  # backend/tests/fixtures/commercial_db/

    async def fetch(self, external_id: str) -> RawDocument:
        return _load_fixture_document(external_id)

    async def sync(self, since=None) -> SyncReport:
        return SyncReport(added=0, updated=0, failed=0, note="mock — no real sync")
```

Registered exactly like a real source; the rest of the system (retrieval, agents, UI) cannot tell the difference structurally, which is what lets Contract/Research agents be built and evaluated before any commercial licensing deal closes.

## 5. Source priority

See [LEGAL-RAG.md](LEGAL-RAG.md) §7 for the hierarchy used at reasoning time (Constitution → federal law → ... → secondary sources). The connector layer doesn't rank; it only ingests and tags provenance. Ranking is a retrieval/reasoning concern, kept separate so a new source doesn't require touching agent code.

## 5a. Real-source investigation (Phase 2, §14 of the brief — findings, not assumptions)

Researched via web search / official documentation before writing any connector code. No scraper was built "just to have one" — per §14 of the Phase 2 brief.

| Source | Official API? | Format | Auth | Verdict |
|---|---|---|---|---|
| **pravo.gov.ru** (`publication.pravo.gov.ru`) — official legal-act publication portal | **Yes** — a documented, read-only API exists at `publication.pravo.gov.ru/help` for listing publication blocks/sub-blocks and retrieving published acts. | Structured (portal-defined), read-only | Not fully confirmed from documentation alone — needs a live registration/dev pass to nail down exactly | **Adapter boundary prepared** (`OfficialLawSource`), real client implementation is Phase 2b/3 work once the exact request/response contract is confirmed against a live endpoint, not assumed from a doc page. |
| **kad.arbitr.ru** (arbitration case card index) | **No official public API.** Every "API" surfaced by search is a third-party commercial reseller (parser-api.com, api-assist.com, etc.) scraping/reselling the public web UI — not sanctioned by the court system. | N/A | N/A | **Do not connect.** Building against unofficial resellers would violate the no-unlicensed-scraping rule (LEGAL-SOURCES.md §1) even though *we* wouldn't be the one scraping — we'd be laundering someone else's scrape. `CourtSource` stays a `NotImplementedError` stub until an official channel exists. |
| **egrul.nalog.ru** (ФНС — official ЕГРЮЛ/ЕГРИП lookup) | It's an **official free ФНС web service**, but it's a form-based single-lookup UI (INN/OGRN/name → signed PDF extract), not a documented bulk/programmatic JSON API. All JSON/XML "APIs" found are third-party resellers of the same data. | PDF (signed), per-lookup | None for the web form | **Adapter boundary prepared** (`TaxSource`), real implementation deferred to Phase 5 (Due Diligence) — needs a decision on whether per-lookup form automation (not scraping, using the service as designed) is acceptable, or whether to wait for a formal ФНС open-data/API program. |
| Other Rosreestr / ФАС / Банк России / Минюст sources named in the brief | Not yet investigated | — | — | Deferred — no connector code written for sources that haven't been checked; investigate before implementing, not after. |

None of this investigation is treated as "the connector is basically done" — every row above is either a documented boundary with a `NotImplementedError` (§14) or explicitly deferred. See §14 in the final Phase 2 report for the same table framed as REAL / ADAPTER-ONLY / NOT POSSIBLE.

## 5b. Phase 5 revision note

Superseded/extended by [LEGAL-SOURCE-MATRIX.md](LEGAL-SOURCE-MATRIX.md), which widens the investigation to ВС РФ, КС РФ, Росреестр, ФАС, Минюст, ЦБ РФ, and the commercial DBs, and adds `OfficialLawSource` as a real (but not yet live-verified) HTTP client against `publication.pravo.gov.ru`'s documented `/api/PublicBlocks/`/`/api/Categories` endpoints — see that document's §4 for why it stopped short of `fetch()`. `LegalSource` gained `is_licensed` (independent from `is_official`/`is_mock` — brief §13).

## 5c. Phase 6 revision note

Re-attempted live verification of `publication.pravo.gov.ru` with both `WebFetch` and a direct `curl`. General internet egress works from this environment (confirmed against `api.anthropic.com`), but `publication.pravo.gov.ru` specifically returns a connection failure (`curl` exit/status `000`) on every attempt — the `.gov.ru` domain itself appears blocked at the network level for this sandbox, not a formatting or auth problem. `OfficialLawSource` status stays `ADAPTER_ONLY / UNVERIFIED` for exactly this reason — no proxy or alternate route was used to work around it (brief §8 explicitly forbids that). No status change until this is checked from a network that can actually reach the host.

## 6. Ingestion pipeline (brief §35)

```
Upload/Fetch
  → OCR (scanned PDFs/images)
  → Text extraction (PyMuPDF / python-docx, matching jarvis's existing document-service deps)
  → Structure detection (article/clause boundaries, court decision sections)
  → Chunking (semantic, article/clause-aware — never mid-sentence for normative text)
  → Metadata extraction (jurisdiction, effective dates, source)
  → Embedding
  → Legal indexing (EmbeddingChunk + full-text index)
```
Runs in the `knowledge-ingest` Celery worker (LEGAL-ARCHITECTURE.md §2). User document ingestion (`UserDocumentSource`) runs the same pipeline but writes to tenant-scoped tables only, never the shared public KB.

## 7. Admin visibility (brief §41)

The Admin Panel (`/api/v1/legal/sources`, `/admin`) surfaces per-source: documents indexed, last sync, index/embedding status, sync errors — with `sync` / `reindex` / `validate` actions per source. This is what makes "is our knowledge base current" answerable without reading logs.

## 8. Phase 7 revision note

Re-verified `publication.pravo.gov.ru` reachability before any Phase 7 work (brief §19 explicitly requires re-checking, not assuming last session's finding still holds). Unchanged: `curl` against `https://publication.pravo.gov.ru/api/PublicBlocks/` still returns connection status `000`; the same control request to `https://api.anthropic.com` still returns a normal `404` in under a second. **Status remains `ADAPTER_ONLY / UNVERIFIED` — no change.** No workaround, proxy, or unofficial mirror was used or considered.
