# LEGAL AI BUREAU — Implementation Roadmap

## Phase 0 — Audit (done)

Findings:
- `E:\Проекты\jarvis` monorepo already runs the target stack: FastAPI + SQLAlchemy(async) + Alembic + Postgres/pgvector + Redis + Celery + Anthropic/OpenAI SDKs, Next.js 14/React/TS/Tailwind frontend, Docker Compose deploy. Confirms [LEGAL-ARCHITECTURE.md](LEGAL-ARCHITECTURE.md)'s stack choice isn't arbitrary — it matches proven operational patterns already running in production for this user.
- `jarvis/agents/legal-agent/src/agent.py` exists but is a bare LLM+tools stub with broken imports (`services.jarvis_core2`, real path is `services/jarvis-core`) — not wired into the live orchestrator, effectively dead code. **Decision: leave untouched**, per explicit instruction — it's out of scope, not a dependency of this build.
- Reusable *patterns* (not imports — see [LEGAL-ARCHITECTURE.md](LEGAL-ARCHITECTURE.md) §8 for why this is a separate repo): `services/jarvis-core/src/orchestrator/` agent-router/tool-manager shape, `services/knowledge_base/` pgvector RAG precedent, `apps/backend/src/api/auth.py` + `middleware/auth_middleware.py` auth shape.
- **Decision: new standalone repo** at `E:\Проекты\legal-ai-bureau`, integrated with Jarvis only via API in Phase 7.

## Phase 1 — Architecture (this doc set — done)

- [LEGAL-PRD.md](LEGAL-PRD.md), [LEGAL-ARCHITECTURE.md](LEGAL-ARCHITECTURE.md), [LEGAL-DATABASE.md](LEGAL-DATABASE.md), [LEGAL-AGENTS.md](LEGAL-AGENTS.md), [LEGAL-RAG.md](LEGAL-RAG.md), [LEGAL-SOURCES.md](LEGAL-SOURCES.md), [LEGAL-SECURITY.md](LEGAL-SECURITY.md), [LEGAL-API.md](LEGAL-API.md), this roadmap.

## Phase 2 — Core Engine

Goal: the anti-hallucination spine works end-to-end before any product surface is built on top of it.

1. Repo scaffold (`backend/`, `frontend/`, `infrastructure/` per [LEGAL-ARCHITECTURE.md](LEGAL-ARCHITECTURE.md) §3), Docker Compose, Alembic baseline migration for all [LEGAL-DATABASE.md](LEGAL-DATABASE.md) tables.
2. `LLMGateway` + provider abstraction + prompt registry (LEGAL-ARCHITECTURE.md §4–5).
3. `OfficialLawSource` + `CourtSource` real connectors (public RU sources) + `CommercialLegalDBSource` mock + ingestion pipeline (LEGAL-SOURCES.md).
4. Legal Knowledge Base populated with a starter RU corpus (ГК РФ core articles + a case-law sample) — enough to exercise retrieval, not full coverage.
5. Hybrid retrieval + temporal retrieval (LEGAL-RAG.md §1–3).
6. Research Agent + reasoning pipeline skeleton (LEGAL-AGENTS.md §2–3).
7. Citation Validator + Confidence system (LEGAL-RAG.md §4–5) — **hard gate before Phase 3**, since every later feature depends on it.
8. Legal Reviewer Agent + Draft→Review→Correction wiring (LEGAL-AGENTS.md §5).
9. Risk Engine (`RiskItem` generation + Risk Matrix aggregation).

Exit criterion: a research question against the seeded corpus returns a `LegalResearchReport` with verified citations end to end, through the real API.

## Phase 3 — Contract Intelligence

1. Document ingestion for PDF/DOCX/TXT/scans (OCR).
2. Contract Agent (parse → structure: parties, subject, obligations, term, payment, liability, termination, IP, confidentiality, jurisdiction).
3. Contract Risk Agent + clause-level risk scoring, Contract Score.
4. Redline/diff (Original vs AI-proposed).
5. Contract generation (`/generate-contract`) with mandatory two-lawyer pipeline.
6. Frontend: Contract Analyzer page ([LEGAL-API.md](LEGAL-API.md) shapes → brief §46 layout).

## Phase 4 — Legal Research (product surface)

1. Legal Research page + `/research` endpoint wired to real UI (brief §47 layout).
2. Case Law Analysis + similarity scoring (LEGAL-RAG.md §3).
3. Conflicting case law handling (LEGAL-RAG.md §6).
4. Legal Opinion structured mode (brief §17 — 11-section structure) as a `LegalResearchReport` template variant.
5. Export: PDF/DOCX/Markdown.

## Phase 5 — Corporate + Due Diligence

1. Corporate Agent: ООО/АО entities, protocols, decisions, participant/director changes.
2. `CompanyProfile` + `CorporateEvent` timeline (brief §24).
3. Due Diligence Agent + `/due-diligence` report (corporate, litigation, bankruptcy, enforcement, tax/public signals, licenses).
4. Company page frontend (brief §48 layout).

## Phase 6 — Litigation

1. Litigation Agent: claimant/defendant position building, weak/strong points, counterarguments.
2. Evidence Matrix (`Evidence` entity, brief §21).
3. Legal Deadline Engine (`Deadline` entity, calendar/procedural-rule based, never ad hoc — brief §34).
4. Claims/pleadings/motions generation via Legal Document Agent.
5. Case management UI + dashboard.

## Phase 7 — Jarvis Integration

1. `jarvis_connector.py` + `/tasks` dispatch endpoint (LEGAL-API.md §Jarvis connector contract).
2. Shared auth strategy decision (separate accounts vs SSO — deferred until this phase; not needed for a standalone product).
3. Task routing from Jarvis's orchestrator into Legal AI Bureau as a specialized agent (brief §50).
4. Cross-agent event contract if Jarvis needs to react to Legal AI Bureau state changes (e.g., a new deadline) — only built if a concrete use case exists at this point, not speculatively.

## Testing strategy (brief §66–67, applies from Phase 2 onward, not bolted on at the end)

**Unit**: legal retrieval correctness, temporal filtering, citation validation, risk scoring, document extraction, deadline calculations.

**Integration**: upload→analysis, research→citations, contract→risks, case→strategy — full pipeline runs, not mocked at the agent boundary.

**AI Evaluation** (`backend/tests/eval/`): benchmark dataset — 100 legal questions, 100 contracts, 100 legal clauses, 100 case-law questions, each with expected source / expected legal issue / expected answer characteristics. Metrics tracked per Phase-2-onward build: citation accuracy, source accuracy, retrieval recall, hallucination rate, issue-identification accuracy, contract risk-detection accuracy, temporal accuracy, case-similarity quality. This is the gate that answers "is it actually good," not "does the UI render" (PRD §8).

## Observability & cost control (brief §68–69, built into Phase 2, not deferred)

- AI request logs, latency, token usage, cost, retrieval results, agent execution traces, citation-validation failures — via `structlog` + Prometheus, matching `jarvis`'s existing observability deps.
- Task-class model routing (LEGAL-ARCHITECTURE.md §4) keeps cheap/fast models on classification/extraction, reserving the strongest model for reasoning/review.
- Caching: laws, common searches, embeddings, documents, case retrieval — Redis, matching existing `jarvis` infra.

## Explicit non-milestones (brief §70 — do not build)

One giant prompt · one universal agent · vector-search-only retrieval · unsourced answers · hardcoded legal data · secrets in git · training on client documents · unlicensed scraping of closed databases.

## Revision note — actual Phase 2-6 execution vs. this document's original numbering

The phases as actually executed (Legal Knowledge Infrastructure, Legal Research Engine, Contract Intelligence, Real Legal Knowledge & Semantic Retrieval, Real Embeddings + Source Verification) diverged from this document's original Phase 2-7 outline (Core Engine/Contract Intelligence/Legal Research/Corporate+DD/Litigation/Jarvis) as the actual per-phase briefs were issued. This note records that divergence rather than silently rewriting the original outline above.

**Phase 5** built: real source audit (`LEGAL-SOURCE-MATRIX.md`), a defensive (unverified-live) `OfficialLawSource` HTTP client, embedding provider/model-version namespace fields, and a 61-case quantitative retrieval benchmark (Recall@1/5/10, MRR, Citation Recall) with a captured mock-embedding baseline.

**Phase 6** built: a real `OpenAIEmbeddingProvider` (batched, timeout/retry-bounded, fail-fast on missing credentials — not exercised live, no API key available this session), a persisted `embedding_namespace` column + namespace-safe bulk reindex (`LegalChunkIndexer.reindex_all`, `POST /knowledge/reindex`), a retrieval diagnostics endpoint (`POST /search/debug`), and structured retrieval observability (`hybrid_retrieval` log events). Re-verified `publication.pravo.gov.ru` is unreachable from this environment specifically (network-level, not a formatting issue) — status remains `ADAPTER_ONLY / UNVERIFIED`.

**Phase 6.5** built: reindex cost/rate limits (`EMBEDDING_MAX_DOCUMENTS_PER_REINDEX`, `EMBEDDING_MAX_REQUESTS_PER_MINUTE`), the `ready_to_activate` atomic-namespace-activation gate, `python -m app.cli.embedding_smoke_test`, a Contract-model tenant-isolation regression test (Case already had one, Contract didn't), and fixed a real bug found via a fresh-DB upgrade/downgrade/upgrade cycle (migration `0002`'s downgrade used an invalid alembic `drop_constraint` type for a Postgres `EXCLUDE` constraint — never exercised until this cycle, now raw SQL).

**Phase 7** built: real JWT authentication + real `WorkspaceMembership`-backed workspace authorization (the `User`/`WorkspaceMembership`/`Role` tables already existed in the schema since Task #10, just never enforced — wiring them in required no new migration), `POST /auth/token`, real `structured_generate()` for both Anthropic (forced tool-use) and OpenAI (native `json_schema` response format) with shared schema-validation/repair/retry in `LLMGateway`, a fail-fast fix for `LLMGateway._build_provider()` (previously silently fell back to mock — same class of bug already fixed for embeddings in Phase 6), a real bug fix for the task-class model-tier routing table (placeholder tier names like `"strong"` were being sent to real provider APIs as literal model names, which would have failed outright), and structural prompt-injection defense (`wrap_untrusted()` delimiting + a fixed, non-interpolated system prompt, regression-tested). Re-verified `publication.pravo.gov.ru` is still unreachable from this environment — unchanged `ADAPTER_ONLY / UNVERIFIED`.

**Still blocked, Phases 6/6.5/7**: a real embedding provider and a real LLM provider have never been exercised against their live APIs (no credentials supplied in any session so far), and `OfficialLawSource` has never received a real HTTP response (network-blocked sandbox, re-confirmed every phase). These remain the prerequisites for the mock-vs-real benchmark comparison this roadmap's testing strategy calls for, and for a live LLM structured-output/prompt-injection test against a real model.

## Phase 8 — Lawyer Workbench / Productization (done)

Turned the Phase 2-7 backend into a full frontend product surface — Dashboard, Cases, Contracts (full clause/risk/redline tabs), Legal Research (with history + persisted detail), Documents, Companies (honest-unavailable), Knowledge admin (Sources/Index/Search Debug), Settings, and global tenant+public Search — rather than a bare API. Real JWT auth wired into the frontend (`sessionStorage`-backed token, axios interceptors, `AuthGuard`), workspace selection via `GET /auth/me`.

Backend additions required to avoid frontend workarounds (brief §31 — "if the API is missing, fix the backend"):
- `legal_research_reports` table (migration `0008`) + `GET /auth/me`, `GET /research` (list), `GET /research/{id}` (was previously compute-and-discard/NOT IMPLEMENTED)
- `GET /documents` (list) with an honest `status` field (`"uploaded"` only — never a fabricated pipeline stage)
- `PATCH /contracts/{id}/redline/{change_id}` — explicit human accept/reject of a proposed redline; the AI never applies a change itself
- `GET /contracts/{id}/versions`
- `GET /search/global` — tenant (Case/Contract/Document/LegalResearchReport, ILIKE, workspace-scoped) + public Legal Knowledge Base search, each result explicitly type-labeled so tenant and public data are never blended silently

Frontend: `@tanstack/react-query` wired in (was an unused dependency since Task #10), a module-level auth store (not React context, so the axios interceptor can read it synchronously outside the React tree), a shared `StatusBadge` component that never relabels `MOCK` as `VERIFIED`, and a `vitest` test suite (new — the frontend previously had zero test tooling) covering the auth store, the workspace auto-selection logic (single-membership auto-select, multi-membership never silently guesses), and `StatusBadge`'s label integrity.

Real UI gaps stayed honest rather than fabricated: Cases' Facts/Evidence Matrix/Deadlines tabs show "not implemented" text (backing endpoints are genuine 501s); Documents are not linked to Cases in the data model, so the Documents tab says so instead of showing an empty list that implies linkage exists; Companies shows a single explanatory unavailable state instead of empty due-diligence fields.
