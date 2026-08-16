# PHASE 9 AUDIT — Legal AI Bureau

Written by directly inspecting `E:\Проекты\legal-ai-bureau` on 2026-08-13 — not derived from prior phase reports. Where a claim below could be verified by running a real command (ruff/mypy/pytest/grep/wc), the command output is quoted or paraphrased; where it could not (Docker was down this session — see §20), that is stated explicitly as `UNVERIFIED THIS SESSION`, not assumed either way.

## 1. Current architecture

FastAPI monolith (`backend/app/`), Next.js 14 App Router frontend (`frontend/`), single Postgres 16 + pgvector, no separate services. Layout: `api/v1/*` (routers, thin) → `domains/*` (business logic) → `models/*` (SQLAlchemy) + `repositories/*` (workspace-scoped data access) + `rag/*` (retrieval) + `llm/*` (provider abstraction) + `security/*` (auth). This matches `LEGAL-ARCHITECTURE.md`'s stated shape. No microservices, no message queue in active use (see §3 on Celery/Redis).

## 2. Current database state

9 migrations, `0001` through `0008` plus the review-perf one (`0005`), all present under `backend/migrations/versions/`. Alembic head is `0008_legal_research_reports` by file inspection (no live DB reachable this session to run `alembic current` — see §20). Tables: organizations/workspaces/users/roles/memberships, cases/documents/evidence/legal_issues/legal_risks, contracts/contract_versions/contract_clauses/contract_risks/contract_recommendations/alternative_clauses/redline_changes/contract_reviews, legal_sources/law_versions/embedding_chunks, legal_research_reports. No tables exist yet for: due diligence reports, company profiles, litigation strategy/timeline, corporate structure/resolutions, generated documents, case facts, deadlines, evidence-matrix aggregation rows (Evidence table exists but nothing populates it), audit log entries (an `AuditLog` model reportedly exists per prior docs but nothing writes to it — everything today is `structlog` events only, not a queryable audit trail).

## 3. Current API surface

9 routers aggregated in `app/api/v1/router.py`: `auth`, `chat`, `research`, `contracts`, `cases`, `companies`, `documents`, `knowledge`, `admin`. Exactly **32 explicit `501 NOT IMPLEMENTED` returns** across these routers (grep-verified) — a genuinely large fraction of the documented surface. Every route depends on `get_current_user`/`get_workspace_id`/`require_role`; there is no route that skips auth. No API versioning strategy beyond the `/v1` prefix (fine for now, not a blocker).

## 4. Current frontend surface

Real pages under `frontend/app/`: `/`, `/login`, `/dashboard`, `/cases`, `/cases/[id]`, `/contracts`, `/contracts/[id]`, `/research`, `/research/[id]`, `/documents`, `/companies`, `/knowledge`, `/knowledge/sources`, `/knowledge/index`, `/knowledge/search-debug`, `/settings`, `/settings/workspace`, `/settings/security`, `/search`. Two orphaned routes still exist (`/chat`, `/litigation`) — not linked from the sidebar, left over from earlier scaffolding, rendering `PlaceholderView`. `npm run build` succeeds (21 routes compiled). Zero test tooling existed before this session; `vitest` was added with 11 tests (auth-store, `useAuth` workspace auto-select, `StatusBadge`) — still a thin slice, not real coverage of the product surfaces.

## 5. Current agent system

**This is the single biggest gap between the roadmap's stated ambition and reality.** `app/agents/` contains 9 agent directories (`compliance`, `contract`, `contract_risk`, `corporate`, `document`, `due_diligence`, `legal_risk`, `litigation`, `research`, `reviewer`, `orchestrator`) — every single one is a **25–33 line Protocol-conforming stub** (line-count verified: `wc -l` on all agent files gives 25–33 lines each). None of them contain real reasoning logic. The actual working intelligence lives elsewhere, outside this `agents/` package entirely:
- Legal Research: `app/domains/legal_research/engine.py` + 10 supporting modules (fact extraction, issue identification, retrieval pipeline, reasoning, counterargument, conflict detection, review, confidence) — **real, substantial, tested**.
- Contract Intelligence: `app/domains/contracts/engine.py` + 13 supporting modules (structure extraction, risk detection, scoring, two-lawyer review, redline, recommendations) — **real, substantial, tested**.

So "the agent system" as architecturally named in `app/agents/` is decorative — a Phase 1 scaffold that later phases never filled in, because the real logic was built as domain services instead. This is not necessarily wrong (domain services are simpler and this codebase explicitly avoids overengineering), but it means Task 8's "audit the existing agents, complete specialized agents where actually necessary" should conclude: **the stub `agents/` package should either be deleted (it's dead code that misleads readers into thinking litigation/corporate/due-diligence logic exists) or the two working domains should be the template for any new one** — not "flesh out the stubs," which would just be adding a second, parallel, thinner architecture next to the one that actually works.

## 6. Current LLM architecture

`app/llm/routing/gateway.py` (`LLMGateway`) + `app/llm/providers/{anthropic,openai}_provider.py` + `MockLLMProvider`. Real `structured_generate()` for both Anthropic (forced tool-use) and OpenAI (native `json_schema`), shared retry/repair/validation via `jsonschema`. `_build_provider()` fails fast (raises `LLMProviderError`) rather than silently falling back to mock when a real provider is configured but misconfigured — this was a real bug fixed in Phase 7 and is still correct on inspection. **Never exercised against a live Anthropic/OpenAI API in any session to date** (no API key ever supplied) — `REAL` by code, `UNVERIFIED` by live test, every phase.

## 7. Current RAG architecture

`HybridRetriever` (RRF fusion of `PostgresKeywordRetriever` + `PgVectorRetriever`), `CitationValidator` (temporal + existence checks), `embedding_namespace()`-scoped storage so provider/model changes never corrupt old data, `LegalChunkIndexer.reindex_all()` with a cost ceiling (`EMBEDDING_MAX_DOCUMENTS_PER_REINDEX`) and a `ready_to_activate` gate. `OpenAIEmbeddingProvider` exists and is real code, but — same as the LLM providers — **never exercised against the live OpenAI embeddings API**. The retrieval benchmark framework (`tests/evals/legal_retrieval/`) exists with a captured mock-embedding baseline; no real-embedding benchmark run exists because no credentials have ever been available.

## 8. Current authentication

Real JWT (`python-jose`, HS256) + `passlib`/bcrypt password hashing + `WorkspaceMembership`-backed authorization, `POST /auth/token`, `GET /auth/me`. `AUTH_DEV_MODE` bypass only fires when environment != production AND no `Authorization` header is present at all (malformed header always 401). This part is solid.

**Found this session, not previously documented as a risk: `jwt_secret` in `app/config/settings.py` has a hardcoded insecure default (`"dev-only-insecure-secret-change-me"`) with no startup check that it was overridden before running with `ENVIRONMENT=production`.** The settings module's own docstring claims "No secret ever has a default value here" — this field directly violates that stated invariant. A production deployment that forgets to set `JWT_SECRET` boots successfully and silently signs tokens with a secret that is public in this repository's source code, meaning anyone can forge a valid token for any user/workspace. This is the most serious concrete finding of this audit (see Task 1 fix below).

## 9. Current tenant isolation

`WorkspaceScopedRepository` base class; `get_workspace_id()` returns identical 403 for "workspace doesn't exist" and "no membership" (no enumeration). `tests/security/test_tenant_isolation.py` exists with 7 tests including a structural check that the public Legal Knowledge Base tables carry no `workspace_id` column at all (can't leak by construction, not just by query discipline). This is genuinely solid, verified by reading the test file and the repository base class, not just trusting a prior report.

## 10. Current document pipeline

`app/documents/` has 5 subpackages (`chunking`, `extraction`, `ingestion`, `ocr`, `storage`) — **4 of them are empty `__init__.py` files with zero implementation**. Only `storage/local_storage.py` exists (21 lines) and it explicitly does not validate size or type before writing to disk (its own docstring admits this). `POST /documents` checks file extension against an allow-list but never validates actual content (no magic-byte/MIME sniffing — a `.pdf` extension with arbitrary bytes inside is accepted), and enforces **no size limit at all**. `GET /documents/{id}/text` is a real `501`. This matches what Phase 8 said honestly in the UI ("text extraction unavailable"), but the missing upload-size limit is a genuine, previously-undocumented DoS vector (Task 1/2 material).

## 11. Current contract workflow

Real and substantial (see §5). Full pipeline: upload → structure/clause extraction → risk detection (multiple specialized detectors) → Legal Research–verified citations → two-lawyer review → recommendations/alternative clauses → word-level redline with explicit human Accept/Reject (`PATCH /contracts/{id}/redline/{change_id}`, added Phase 8) → versioning. This is the most complete product surface in the repository.

## 12. Current research workflow

Real and substantial (see §5). Now persisted (Phase 8: `legal_research_reports` table, list + detail endpoints). Structured trace excludes chain-of-thought by construction (the trace dataclass only carries queries/counts/timings/knowledge-snapshot, there's no field a prompt could leak into).

## 13. Current source integration

`app/sources/` — `mock/` has a real 65-line base + 270-line mock dataset (used throughout tests); `official/official_law_source.py` (121 lines) is a defensive HTTP client for `pravo.gov.ru`, **re-confirmed unreachable from this sandboxed network in every phase to date, including this one is UNVERIFIED (not re-tested this session, no network egress attempted)**; `courts/`, `tax/`, `commercial/` are each 25–39 line adapter-boundary stubs with no real HTTP integration — LEGAL-SOURCES.md already documents this honestly as "adapter-boundary-only." Nothing here has regressed or improved since the last phase's documentation; the matrix in `LEGAL-SOURCE-MATRIX.md` should still be treated as current.

## 14. Current real-vs-mock matrix (see full table in `docs/LEGAL-REALITY-MATRIX.md`, written alongside this audit)

Summary: Legal Research reasoning/retrieval/citation-validation = REAL (mock data, real logic). Contract Intelligence = REAL (mock data, real logic). LLM providers (Anthropic/OpenAI) = REAL code, UNVERIFIED live. Embeddings (OpenAI) = REAL code, UNVERIFIED live. Official law source = ADAPTER_ONLY (network-blocked). Court/tax/commercial sources = ADAPTER_ONLY, no real HTTP client. Company/Due-Diligence = NOT_IMPLEMENTED (honestly, in the UI too). Litigation strategy/corporate/document-generation = NOT_IMPLEMENTED (agent stubs only, no domain logic, no endpoints beyond a handful of 501s). Document text extraction/OCR = NOT_IMPLEMENTED.

## 15. Security risks (verified this session, not assumed)

1. **`jwt_secret` has an insecure default with no production fail-fast check** (§8) — highest severity, concrete, exploitable if ever misdeployed.
2. **No CORS middleware anywhere in the codebase** (`grep -rln "CORSMiddleware" app/` → zero hits) — the browser frontend (different origin in any real deployment) has no configured allowed-origins policy at all. In practice this either breaks the app in production or (if someone "fixes" it by wildcarding `*` under pressure) becomes a much worse hole; needs a real fix, not a workaround.
3. **No rate limiting anywhere** (`grep` for `slowapi`/`rate.limit` → zero hits, not a dependency). `POST /auth/token` and `POST /research`/`POST /contracts/{id}/analyze` (both call paid LLM APIs when configured) are unprotected against brute-force/cost-abuse.
4. **No upload size limit** (§10) — unbounded request body on `POST /documents`.
5. **No content-based file-type validation** — extension allow-list only, no magic-byte check.
6. Celery + Redis are installed dependencies with **zero actual usage** anywhere in `app/` — dead attack surface / dead weight, not a vulnerability per se, but worth removing rather than leaving an unused broker connection string as a red herring in `.env.example`.
7. Error responses were not individually re-audited for stack-trace leakage this session (would require live requests against a running server — blocked, see §20); FastAPI's default exception handling does not leak tracebacks unless `debug=True`, and `Settings.debug` defaults to `False`, so this is likely fine but **UNVERIFIED live**.

## 16. Product gaps

Company/Due Diligence, Litigation strategy workspace, Corporate legal workspace, standalone document generation — all genuinely unbuilt (not just UI placeholders; there is no backend domain logic for any of them, confirmed by directory inspection in §5/§10). Case workspace's Facts/Evidence-Matrix/Deadlines tabs are honest 501-passthroughs. Global search is real but ILIKE-only for tenant data (no ranking, no fuzzy match) — fine for now, worth revisiting only if usage shows it's a problem.

## 17. UX gaps

No global loading/error/empty-state system (each view rolls its own inline `isLoading`/`isError` handling — functional but not shared, so it's easy for a new view to forget an edge case). No keyboard shortcuts. No audit-trail UI anywhere despite audit *events* existing (structlog only, not queryable — see §2).

## 18. Performance risks

Not independently re-benchmarked this session (would need a live DB + load, see §20). Known from Phase 6.5: one N+1 was found and fixed in `LegalConflictDetector`; no other systematic N+1 audit exists for the newer Phase 8 endpoints (`/search/global` runs 4 separate tenant queries + 1 retrieval call per request — acceptable at current scale, would need pagination/indexing attention if tenant tables grow large; no index currently exists on `Case.title`/`Contract.title`/`LegalResearchReport.question` for the `ILIKE` pattern, meaning `/search/global` will sequential-scan those tables — fine today, a real risk once a workspace has thousands of cases/contracts).

## 19. Missing legal workflows

Document generation (contracts/claims/POAs from templates+facts), litigation drafting (claim/response/objection), corporate document generation, due-diligence report generation — all absent, matching §16.

## 20. Recommended implementation order

Given the actual state above (not the aspirational Phase 9 brief's full 28-task list, which is realistically several weeks of work), the highest-value, lowest-risk next increment is:

1. **Fix the concrete security findings from §15** (JWT secret fail-fast, CORS, upload size limit, rate limiting on auth/LLM-cost endpoints) — bounded, mechanical, high value, no new product surface. **This audit's own companion PR does this — see PHASE-9-RESULT.md.**
2. **Real document text extraction** (PDF/DOCX/TXT via existing well-known libraries, no OCR) — unblocks Document Q&A and is a prerequisite for any of Tasks 3/4/6/7 that reference uploaded documents.
3. **Due Diligence connector investigation** (like the Phase 2 `pravo.gov.ru`/`kad.arbitr.ru` investigation already in `LEGAL-SOURCE-MATRIX.md`) before writing any Due Diligence domain code — building fabricated-looking company data would violate the project's core "never fabricate" principle worse than not building the feature at all.
4. Litigation and Corporate domains, following the Contract/Research domain-service pattern (not the empty `agents/` package) — only after 2 and 3, since both plausibly need real document ingestion and real external data first to be more than another honest-501 surface.
5. Document generation, last — it depends on 2 (facts must come from somewhere) and should reuse the Legal Research engine for its legal-basis grounding rather than inventing a third reasoning pipeline.

**Infrastructure note (blocks nothing above, but blocks verification):** Docker Desktop was unreachable for most of this session (`docker ps` hung for 20+ minutes despite the process running) — `alembic upgrade head` against a live DB, the 223 DB-dependent tests, and any live smoke test are marked `UNVERIFIED THIS SESSION` throughout, not assumed passing. `ruff check .` (178 files), `mypy app` (178 files), the 209 DB-independent unit tests, and the full frontend gate (`lint`/`type-check`/`build`/`vitest`) all ran clean and are genuinely verified.
