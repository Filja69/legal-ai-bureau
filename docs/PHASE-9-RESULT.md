# PHASE 9 RESULT — Legal AI Bureau

Scope note up front, honestly: the Phase 9 brief specified 28 tasks spanning a full document-intelligence pipeline, document generation, due diligence, litigation, corporate legal workflows, a real agent system, and more — realistically several weeks of work. This session completed **Task 0 (audit) and Task 1 (production security blockers)** in full, verified, with real numbers below. Tasks 2–9 (document pipeline, generation, due diligence, litigation, corporate, full agent system, evidence panel, two-lawyer-review strengthening) were **not attempted** — building any one of them for real, without fabricating a hollow stub, is itself a multi-session effort, and the audit's own recommended order (§20) says document text extraction should come first regardless. Faking partial versions of all nine would have violated this project's core "never fabricate to look complete" principle applied to my own output, so I did not.

## 1. Completed

- `docs/PHASE-9-AUDIT.md` — 20-section audit written from direct repository inspection (line counts, grep results, actual file contents), not from trusting prior phase reports. Key finding: `app/agents/` (litigation/corporate/due-diligence/document/etc.) is entirely 25–33-line Protocol stubs; the real intelligence lives in `app/domains/legal_research` and `app/domains/contracts`.
- `docs/LEGAL-REALITY-MATRIX.md` — capability-by-capability REAL/MOCK/ADAPTER_ONLY/BLOCKED/NOT_IMPLEMENTED table.
- **Fixed a genuine, previously-undocumented security bug**: `jwt_secret` had an insecure hardcoded default with no check preventing a production deployment from booting with it. `Settings.assert_production_safe()` now refuses to start if `ENVIRONMENT=production` and either the JWT secret is still the dev default or `DEBUG=true`.
- **Added CORS policy** — zero `CORSMiddleware` usage existed anywhere before this session; now configurable via `CORS_ALLOWED_ORIGINS`.
- **Added upload size limit** — `POST /documents` previously had no bound on request body size; now streams in 1 MB chunks and rejects >25 MB (configurable) with `413`, never buffering an oversized file fully in memory.
- **Added rate limiting** — `POST /auth/token` (per client IP, brute-force protection) and `POST /research` / `POST /contracts/{id}/analyze` (per workspace, cost-abuse protection on paid-LLM-calling endpoints). In-process, documented as a single-instance-only fix (Redis exists as a dependency but has zero other usage in the codebase, so wiring it in now would be new infrastructure without the multi-instance need that would justify it).
- `docs/PRODUCTION-READINESS.md` — full READY/PARTIAL/BLOCKED/NOT_READY matrix.

## 2. Files changed

`backend/app/config/settings.py` (new fields + `assert_production_safe()`), `backend/app/main.py` (CORS middleware + startup check call), `backend/app/api/v1/documents.py` (bounded upload read), `backend/app/api/v1/auth.py` (rate limit dependency), `backend/app/api/v1/research.py` (rate limit dependency), `backend/app/api/v1/contracts.py` (rate limit dependency), `backend/app/security/rate_limit.py` (new), `backend/tests/unit/test_configuration.py` (+6 tests), `backend/tests/unit/test_rate_limit.py` (new, 4 tests), `.env.example` (new security section).

## 3. Database

No schema changes this session — no migration added or needed.

## 4. APIs

No new endpoints. Behavior changes only: `POST /auth/token` now `429`s after 10 requests/minute/IP (configurable); `POST /research` and `POST /contracts/{id}/analyze` now `429` after 20 requests/minute/workspace (configurable); `POST /documents` now `413`s above 25 MB (configurable) instead of accepting unbounded uploads.

## 5. Frontend

No changes this session.

## 6. Security

See §1. Three concrete gaps closed (JWT secret fail-fast, CORS, rate limiting) plus one (upload size) that was a real DoS vector with no prior tracking. Not addressed this session, tracked in the audit as remaining: content-based (magic-byte) upload validation beyond extension checking, and a queryable audit-log writer (events currently only reach `structlog`, not a persisted table despite the `AuditLog` model existing).

## 7. Tests

Backend unit suite (no DB required): **161 passed, 0 failed, 2 errors** (both `test_prompt_injection.py` tests require a live Postgres connection and are `BLOCKED` by the Docker outage, not a code failure — same 2 tests were passing in earlier sessions with Postgres reachable). New tests added this session: 10 (6 in `test_configuration.py`, 4 in `test_rate_limit.py`), all passing.
`ruff check .` — all checks passed (179 files).
`mypy app` — no issues found (179 source files).
Frontend: `npx vitest run` — **3 test files, 11 tests, all passed.**
223 DB-dependent backend tests (integration/security suites) — **BLOCKED**, not run this session (Docker Desktop unreachable, see §12). No regression evidence either way; these were the tests that individually passed earlier in the Phase 8 session when Postgres was briefly reachable.

## 8. REAL / MOCK / BLOCKED

Full table in `docs/LEGAL-REALITY-MATRIX.md`. No entries changed status this session except the security-gap rows, which moved from `NOT_READY` to fixed-and-unit-tested-but-not-live-verified (see §12).

## 9. Problems found

1. `jwt_secret` insecure default, no production fail-fast (security, fixed).
2. No CORS policy anywhere (security, fixed).
3. No rate limiting anywhere (security, fixed).
4. No upload size limit (security, fixed).
5. `app/agents/` package is entirely decorative stubs, contradicting what the directory name implies exists (architecture/documentation bug — flagged in the audit, not fixed this session; recommend either deleting the stub package or treating `app/domains/{legal_research,contracts}` as the template for future agent work, not filling in the stubs as a parallel structure).
6. Celery + Redis are declared dependencies with zero actual usage (dead weight, not a vulnerability — flagged, not removed this session to avoid scope creep on a security-focused pass).
7. Docker Desktop was unreachable for the majority of this session despite its processes running — infrastructure issue, not a code issue (see §12).

## 10. Problems fixed

Items 1–4 above, all backed by new passing unit tests.

## 11. Remaining risks

- The CORS/rate-limit/upload fixes have unit-level coverage but were **never exercised against a live running server this session** (Docker outage) — verify with a real request before considering this closed.
- Rate limiting is single-process/in-memory; if the app is ever deployed behind a multi-instance load balancer, the limits are per-instance, not global, and someone could exceed the intended global rate by hitting different instances.
- Upload validation is still extension-only; a maliciously renamed file (e.g., an executable saved as `.txt`) would pass today.
- No queryable audit trail — `structlog` events are not the same as a persisted, queryable `AuditLog` table for compliance/legal review purposes, and the brief explicitly asked for "audit visibility for sensitive actions."
- `app/agents/` stub package remains in the codebase, misleading about what actually exists there.

## 12. Credentials/network blockers

- **Docker Desktop**: unreachable for ~20+ minutes across multiple restart attempts this session (`docker ps` hung repeatedly despite `Docker Desktop.exe` processes running). Root cause not diagnosed — most likely a stuck first-run/update dialog that needs a human to click through; a background wait cannot resolve this. Blocks: `alembic upgrade head` against a live DB, all 223 DB-dependent tests, any live smoke test.
- **Anthropic/OpenAI API keys**: never supplied in any session to date. Blocks: live LLM structured-generation test, live embedding test, real-vs-mock retrieval benchmark comparison.
- **`pravo.gov.ru` / `kad.arbitr.ru` network access**: not re-attempted this session (network-blocked in every prior session); status carried forward as `ADAPTER_ONLY`, not re-verified.

## 13. Production readiness

**PARTIAL.** See `docs/PRODUCTION-READINESS.md` for the full table. The single most serious pre-existing gap (JWT secret fail-fast) is now fixed and unit-tested. The system is closer to safe-to-deploy than before this session, but is not ready: the CORS/rate-limit/upload fixes need live verification, the DB-dependent test suite needs to actually run once Docker recovers, and several major product surfaces (document intelligence, due diligence, litigation, corporate, document generation) remain entirely unbuilt.

## 14. Recommended next phase

In order:
1. **Verify this session's fixes live** the moment Docker/Postgres is reachable — full `alembic upgrade head`, full 432-test suite, a real smoke test hitting `POST /auth/token` past its rate limit and `POST /documents` past its size limit to confirm the `429`/`413` responses actually fire outside a unit-test mock.
2. **Real document text extraction** (PDF/DOCX/TXT, no OCR) — per the audit's §20, this is the correct next feature because it's a prerequisite for Document Q&A, and partially for Litigation/Corporate/Due-Diligence's document-referencing needs.
3. Only after that: a real source-connector investigation for Due Diligence data (registry lookups) before writing any Due Diligence domain code, following the same honest pattern already used for `pravo.gov.ru`/`kad.arbitr.ru` in `LEGAL-SOURCE-MATRIX.md` — building fabricated-looking company data would be worse than not building the feature.

Not starting Task 2 (or any of Tasks 2–9) automatically, per the brief's own instruction not to declare completion or move on without the Definition of Done actually being verified — it isn't, for the tasks not attempted this session.
