# Legal AI Bureau — Production Readiness

Written 2026-08-13 alongside `docs/PHASE-9-AUDIT.md`; updated 2026-08-14 after Phase 9.2 (Document Intelligence); updated again 2026-08-15 after Phase 9.2.1 (Docker/Postgres recovered, full live verification — `docs/PHASE-9-2-INTEGRATION-VERIFICATION.md`). Every item is graded `READY` / `PARTIAL` / `BLOCKED` / `NOT_READY` against what was actually verified in the session that touched it — see the linked reports for methodology (direct repo inspection, not trust in prior reports).

| Area | Status | Why |
|---|---|---|
| Core architecture | READY | FastAPI/Postgres/SQLAlchemy/Alembic monolith, DDD-ish layering, matches `LEGAL-ARCHITECTURE.md`; no unnecessary services added |
| Authentication (JWT + membership RBAC) | READY | Real, tested (34+ dedicated security tests), malformed/expired/wrong-signature tokens all correctly rejected |
| Secret management | **PARTIAL → fixed this session** | `jwt_secret`'s insecure default now fails startup in production (`Settings.assert_production_safe()`); was previously `NOT_READY` with no check at all |
| Tenant isolation | READY | `WorkspaceScopedRepository` + 7 dedicated tests incl. a structural "public KB has no `workspace_id`" check |
| CORS | **PARTIAL → fixed this session** | `CORSMiddleware` now wired to `CORS_ALLOWED_ORIGINS`; was `NOT_READY` (zero CORS policy existed) — still needs the real production frontend origin(s) set before deploy, not just localhost |
| Rate limiting | **PARTIAL → fixed this session** | In-process limiter on `/auth/token` (per-IP) and `/research`+`/contracts/{id}/analyze` (per-workspace); was `NOT_READY`. Single-process only — needs a Redis-backed limiter before running >1 backend instance |
| Upload limits/validation | **READY (Phase 9.2)** | 25 MB streaming-bounded read, magic-byte + extension/MIME-mismatch detection, ZIP-bomb defense (entry count/ratio/uncompressed-size caps), tenant/document-id-scoped storage paths (original filename never touches the filesystem path) |
| Legal Research engine | READY (mock data) | Full IRAC pipeline, citation-gated, deterministic confidence, 30+ adversarial tests incl. hallucination cases; Phase 9.2 added optional user-selected tenant-document evidence, workspace-verified |
| Contract Intelligence | READY (mock data) | Full clause/risk/redline/two-lawyer-review pipeline, explicit human accept/reject; Phase 9.2 wired real Document→Contract creation |
| Document upload/list | READY | Real storage + listing |
| Document text extraction (PDF text-layer/DOCX/TXT/XLSX) | **READY (Phase 9.2)** | Real `pypdf`/`python-docx`/`openpyxl` extraction, deterministic clause/section structure detection with plain-text fallback, tenant-scoped chunking + indexing (structurally separate from the public KB), idempotent reprocessing |
| OCR (scanned PDF) | NOT_READY (explicitly out of scope) | Honestly reports `ocr_required`; never fakes extraction from a page image |
| Document Q&A / analysis | **READY (Phase 9.2, mock LLM)** | Two-gate evidence requirement (empty retrieval never reaches the LLM; LLM must self-report sufficient evidence); EXTRACTED (regex) vs INFERRED (LLM) fact provenance; prompt-injection-safe (`wrap_untrusted`) — logic verified, live LLM behavior still `UNVERIFIED LIVE` like every other LLM-calling path |
| Company / Due Diligence | NOT_READY | No domain logic exists; UI honestly shows unavailable rather than fabricating |
| Litigation workspace | NOT_READY | `agents/litigation/agent.py` is a 26-line stub; no domain logic, no real endpoints beyond honest 501s |
| Corporate legal workspace | NOT_READY | Same pattern as Litigation |
| Document generation | NOT_READY | No endpoint, no domain logic |
| LLM providers (Anthropic/OpenAI) | PARTIAL | Real code, fail-fast on misconfiguration, **never exercised against a live API in any session** |
| Embeddings (OpenAI) | PARTIAL | Same — real code, `UNVERIFIED LIVE` |
| Official/court/tax/commercial legal sources | BLOCKED / ADAPTER_ONLY | `pravo.gov.ru` unreachable from this sandbox in every session to date; the other three have no real HTTP client written yet |
| Audit trail | PARTIAL | Events exist as `structlog` log lines (auth, redline decisions, research completion); no persisted queryable `AuditLog` writer wired in despite the model existing |
| Frontend (auth/dashboard/cases/contracts/research/documents/knowledge/settings/search) | READY | Real, workspace-scoped, builds clean, lints clean, type-checks clean; Phase 9.2 added the Document detail workspace (Overview/Content/Analysis/Ask/Citations) |
| Frontend tests | PARTIAL | 23 `vitest` tests (was 11): auth-store, workspace auto-select, StatusBadge, DocumentStatusBadge (all 6 states), DocumentDetailView (forbidden/404, retry, OCR vs failed distinction, evidence-gated Ask, citation display). Fixed a real test-isolation bug this session — `vitest.setup.ts` had no DOM cleanup between tests, so multi-test files were silently order-dependent |
| Backend tests | **READY (Phase 9.2.1)** | **512/512 passed against real Postgres** — full suite, no filter, 0 failures. Two real bugs found and fixed in the process (naive/aware datetime mismatch; fallback-chunking provenance loss) — see `docs/PHASE-9-2-INTEGRATION-VERIFICATION.md` §14 |
| Database migrations | **READY (Phase 9.2.1)** | 10 migrations; `alembic current` confirms `0009_document_intelligence (head)` actually applied on the live dev DB |
| Docker / infra | **READY (Phase 9.2.1)** | Recovered this session after being `BLOCKED` in the two immediately preceding sessions; root cause of the prior outages still not diagnosed (may recur) |
| Observability | PARTIAL | Structured request-latency logging exists (`X-Request-Id`, `request_completed` events); Phase 9.2 added `document_processed` events (id/workspace/chunk_count/extractor, never document content). No metrics export (Prometheus/etc.), no token-usage/cost tracking |

## Overall: **PARTIAL — infrastructure and Document Intelligence are now live-verified; the remaining gap to production is entirely product-scope decisions and live LLM credentials, not unverified code.**

Blocking items before a real production deploy, in priority order:
1. A decision on Due Diligence/Litigation/Corporate: build them for real (multi-session effort, needs source-connector investigation first per the audit's §13/§20) or keep them explicitly out of v1 scope.
2. A live LLM/embedding smoke test against real Anthropic/OpenAI credentials — every phase to date has shipped this as `UNVERIFIED LIVE`, including Document Q&A/analysis's LLM-dependent half (citation roundtrip specifically cannot be observed under a mock provider — see `docs/PHASE-9-2-INTEGRATION-VERIFICATION.md` §9).
3. OCR, if scanned-document support becomes a real product requirement — architecture already leaves room for a provider to be added later without touching the extraction interface.
4. Diagnose why Docker/Postgres was unreachable for two consecutive sessions before this one recovered — root cause unknown, may recur.
