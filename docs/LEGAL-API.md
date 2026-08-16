# LEGAL AI BUREAU — API Surface

Base path: `/api/v1/legal`. All routes require auth (bearer token) and are workspace-scoped (`X-Workspace-Id` header or path-derived) except `/sources` admin routes which additionally require `Admin`/`Owner` role. Response bodies follow the structured-output contract from [LEGAL-AGENTS.md](LEGAL-AGENTS.md) §7 wherever an AI conclusion is returned.

## Chat (secondary entry point — PRD §5)

### `POST /chat`
```json
// request
{ "message": "string", "case_id": "uuid | null", "attachments": ["document_id"] }
// response
{ "reply": "string", "conclusion_ref": { "type": "research|risk|document", "id": "uuid" } | null }
```
Routes internally to whichever product surface the Orchestrator classifies the message into; the chat response links to the structured result rather than re-deriving it as prose.

## Legal Research

> **Phase 3 revision note:** `/research` is now the real Legal Research Engine
> endpoint (`app/domains/legal_research/engine.py`) — question → fact
> extraction → issue identification → research plan → multi-stage retrieval →
> evidence ranking → IRAC reasoning → counterargument search → conflict
> detection → independent review → deterministic confidence, not the Phase 2
> evidence-only stub. Response shape changed accordingly (`research_id` +
> `status` + nested `result`/`trace`, not the flat `executive_summary` shape
> sketched at Phase 1). `requested_output=case_analysis|second_opinion`
> return `501` — extension points, not implemented (brief §39).

### `POST /research`
```json
// request
{
  "question": "Может ли заказчик отказаться от договора оказания услуг?",
  "jurisdiction": "RU",
  "effective_at": "2026-08-10",
  "facts": ["договор заключен между ООО и ИП"],
  "requested_output": "legal_research"   // quick_answer | legal_research | legal_opinion
}
// response
{
  "research_id": "uuid",
  "status": "completed",              // completed | blocked_unverified_claim | research_failed
  "result": {
    "executive_conclusion": "...",
    "confidence": "high|medium|low",
    "issues": [{"id": "...", "title": "...", "priority": 1, "issue_type": "substantive|procedural"}],
    "facts": [{"subject": "...", "predicate": "...", "source": "user_stated|ai_inferred", "confidence": 1.0}],
    "claims": [{"claim": "...", "claim_type": "rule|conclusion", "importance": "critical",
                "citations": ["ст. 309"], "verification_status": "verified|mock|unverified|unsupported_critical"}],
    "analysis": ["..."],
    "counterarguments": ["..."],
    "conflicts": [{"conflict_type": "jurisprudential_conflict", "position_a": "...", "position_b": "..."}],
    "risks": ["..."],
    "missing_facts": [{"question": "...", "criticality": "critical|important|optional"}],
    "recommended_actions": ["..."],
    "citations": ["ст. 309", "ст. 393"],
    "citation_coverage": 0.93,
    "escalate_to_human": false,
    "escalation_reasons": []
  },
  "trace": { "research_id": "...", "queries": [...], "retrieved_count": 12, "llm_calls": 5,
             "performance_ms": {"retrieval_ms": 42.1, "reasoning_ms": 18.3, "total_ms": 91.4},
             "knowledge_snapshot": {"total_chunks": 12, "mock_chunks": 12} }
}
```

### `GET /research/{id}` — implemented in Phase 8 (see revision note below); results are now persisted. `GET /research` (list) was added alongside it.

## Contract Intelligence

> **Phase 4 revision note:** the flat `/analyze-contract` sketch from Phase 1
> is superseded by a real, persisted, RESTful surface
> (`app/api/v1/contracts.py`, `app/domains/contracts/engine.py`) —
> `Contract`/`ContractVersion`/`ContractClause`/`ContractRisk`/
> `ContractRecommendation`/`AlternativeClause`/`RedlineChange`/
> `ContractReview` are real DB tables, not computed-and-discarded like
> Phase 3's `LegalResearchResult`. `/generate-contract` and
> `/review-document` (standalone document generation, not tied to an
> uploaded contract) remain NOT IMPLEMENTED — Phase 4 only covers
> *analyzing* an existing contract, not drafting one from scratch.

```
POST   /contracts                          — { title, contract_type?, raw_text } -> Contract (document_id path is 501: no OCR/PDF/DOCX extraction yet)
GET    /contracts                          — list, workspace-scoped
GET    /contracts/{id}                     — get
POST   /contracts/{id}/analyze             — { party_perspective?, review_depth?, jurisdiction?, force? } -> runs the full pipeline, idempotent per (version, config) — brief §48
POST   /contracts/{id}/review              — fetch the persisted review for the current version (404 if /analyze hasn't run)
POST   /contracts/{id}/redline             — list RedlineChange rows for the contract (clause-linked, risk-linked, research-linked)
PATCH  /contracts/{id}/redline/{change_id} — { decision: "accepted"|"rejected" } -> explicit human accept/reject (Phase 8)
GET    /contracts/{id}/clauses             — extracted ContractClause rows
GET    /contracts/{id}/risks               — persisted ContractRisk rows
GET    /contracts/{id}/report              — full ContractReviewReport-shaped JSON (risks + recommendations + alternative clauses)
POST   /contracts/{id}/search              — { query } -> ILIKE search over this contract's own extracted clauses
GET    /contracts/{id}/versions            — list ContractVersion rows (Phase 8)
GET    /contracts/{id}/diff?from_version_id=&to_version_id=  — real clause diff (added/removed/changed) between two versions
GET    /contracts/{id}/export/{fmt}        — NOT IMPLEMENTED (501) — DOCX/PDF export, see LEGAL-ROADMAP.md
```

```json
// POST /contracts/{id}/analyze response
{
  "review_id": "uuid", "status": "completed",
  "overall_score": 61, "risk_summary": {"critical": 1, "high": 2, "medium": 4, "low": 6, "info": 0},
  "executive_summary": "...", "analysis_status": "current"
}
```

### Not implemented (Phase 5+ candidates)

```
POST /generate-contract   — standalone document drafting (not tied to an uploaded contract)
POST /review-document     — independent review of a freestanding generated document
```

## Cases (Litigation + general matter management)

```
GET    /cases
POST   /cases
GET    /cases/{id}
PATCH  /cases/{id}
POST   /cases/{id}/facts            — append CaseFact
GET    /cases/{id}/evidence-matrix
POST   /cases/{id}/strategy         — Litigation Agent: claimant/defendant position, weak/strong points
GET    /cases/{id}/deadlines
```

## Companies (Corporate + Due Diligence)

```
GET    /companies
POST   /companies                   — create/track a CompanyProfile (by INN/OGRN/name)
GET    /companies/{id}              — profile + timeline
POST   /due-diligence               — { "inn": "...", "ogrn": "...", "name": "..." } -> full DD report
GET    /due-diligence/{report_id}
```

## Documents (generic ingestion)

```
POST   /documents                   — upload (PDF/DOCX/TXT/XLSX/CSV/image) -> ingestion pipeline
GET    /documents/{id}
GET    /documents/{id}/text         — extracted text
```

## Knowledge base / verification

> **Phase 2 revision note (Legal Knowledge Infrastructure):** `/search` is real
> (`mode=hybrid|exact|semantic`, backed by `HybridRetriever`/`PostgresKeywordRetriever`/
> `PgVectorRetriever` — see LEGAL-RAG.md). `/citations/verify` is real, wired
> to `CitationValidator` v2 (adds `TEMPORALLY_INVALID`/`MOCK` outcomes). The
> admin surface for sources/documents/index status moved to a dedicated
> `/knowledge/*` namespace below instead of overloading `/sources` and
> `/admin/*` — `mode=citation|temporal|case_law` and `GET /citations/{id}`
> remain not-yet-implemented (Phase 3).

```
GET    /search?q=...&mode=hybrid|exact|semantic&jurisdiction=&effective_at=&document_type=&article=&top_k=
GET    /citations/{id}              — NOT IMPLEMENTED (Phase 3) — full citation detail (title, article, redaction, date, source, URL)
POST   /citations/verify            — { "citation_text": "...", "effective_at": "..." } -> CitationCheck (real, LEGAL-RAG.md §4)
GET    /risks?subject_type=&subject_id=
GET    /evidence?case_id=
```

## Knowledge admin (`/knowledge/*` — Phase 2, brief §35, requires Admin/Owner role)

```
GET    /knowledge/sources                       — list LegalSource rows + sync/health status
POST   /knowledge/sources/{id}/sync              — run IngestionPipeline for that source (mock: real; real sources: 501, LEGAL-SOURCES.md §14)
GET    /knowledge/documents?document_type=       — list indexed EmbeddingChunk rows
POST   /knowledge/documents/{chunk_id}/reindex   — re-embed + replace one chunk
GET    /knowledge/index-status                   — total/mock chunk counts, breakdown by document_type
```

## Admin

```
GET    /admin/sources               — NOT IMPLEMENTED (superseded by /knowledge/sources above)
GET    /admin/index-status          — NOT IMPLEMENTED (superseded by /knowledge/index-status above)
GET    /admin/errors                — NOT IMPLEMENTED (Phase 3)
GET    /admin/audit-log?...         — NOT IMPLEMENTED (Phase 3 — AuditLog model already exists)
```

## Jarvis connector contract (Phase 7 — LEGAL-ARCHITECTURE.md §7)

Jarvis calls the same public API, task-shaped:
```json
POST /api/v1/legal/tasks
{ "task": "analyze_contract", "document_id": "...", "jurisdiction": "RU" }
```
```json
// response — same structured shape as /analyze-contract
{ "status": "completed", "result": { ...AnalyzeContractResponse } }
```
`/tasks` is a thin dispatch wrapper added only in Phase 7, mapping `task` names to the existing typed endpoints above — no separate business logic.

## Revision note — real authentication (the actually-executed "Phase 7", distinct from the `/tasks` reference above — see LEGAL-ARCHITECTURE.md §9)

`Base path` line above ("All routes require auth (bearer token)... `Admin`/`Owner` role") is now literally true, not aspirational — every route depends on `get_current_user`/`get_workspace_id`/`require_role` (`app/security/deps.py`), which perform real JWT verification and real `WorkspaceMembership` checks.

**New**: `POST /api/v1/legal/auth/token`
```json
// request
{ "email": "string", "password": "string" }
// response
{ "access_token": "string", "token_type": "bearer", "expires_in_minutes": 720 }
```
`401` on unknown email or wrong password (identical response for both — no email enumeration). Send the token as `Authorization: Bearer <token>` on every subsequent request; `X-Workspace-Id` is still required on workspace-scoped routes, but is now verified against a real membership, not merely read.

`POST /api/v1/legal/search/debug` (Phase 6) and `POST/GET /api/v1/legal/knowledge/*` (Phase 2 admin surface) both require `Admin`/`Owner` — this was already documented, now actually enforced against a real per-membership role rather than a stub that always returned `Owner`.

## Revision note — Phase 8 (Lawyer Workbench/Productization) API additions

The frontend product surfaces (Dashboard/Cases/Contracts/Research/Documents/Knowledge/Settings/Search) needed a few endpoints that either didn't exist or were stubs; all were added as real, tested, workspace-scoped implementations — no frontend workaround was built for a missing API (brief §31).

**New**: `GET /api/v1/legal/auth/me`
```json
// response
{
  "user_id": "uuid", "email": "string|null", "name": "string|null",
  "is_dev_bypass": false,
  "memberships": [{"workspace_id": "uuid", "workspace_name": "string", "role": "admin|owner|member|..."}]
}
```
Used to build the workspace selector and gate admin-only UI (Knowledge). Under `AUTH_DEV_MODE`, returns `is_dev_bypass: true` and an empty `memberships` array (dev bypass doesn't track real membership rows).

**Changed**: `POST /research` now persists its result to a new `legal_research_reports` table (migration `0008`) instead of computing-and-discarding. `research_id` in the response is now the persisted row's id.

**New**: `GET /research?case_id=&limit=&offset=` — paginated list of past research reports for the workspace (`{"total": int, "items": [...]}`), newest first.

**Implemented**: `GET /research/{id}` — previously documented as NOT IMPLEMENTED above; now returns the persisted report (`{research_id, status, result, trace, created_at}`). `404` for both "doesn't exist" and "exists in another workspace" (no cross-tenant existence signal, matching LEGAL-SECURITY.md §2).

**New**: `GET /documents` — list documents for the workspace. Every row's `status` is `"uploaded"` — never a fabricated `"processing"`/`"analyzed"`, since OCR/text-extraction (`GET /documents/{id}/text`) is still `501`.

**New**: `PATCH /contracts/{id}/redline/{change_id}` — `{"decision": "accepted"|"rejected"}` -> `{"id", "review_status"}`. The explicit human accept/reject action for a proposed `RedlineChange`; the AI never applies a redline to the document itself, only this endpoint (triggered by a user click) changes `review_status`. `400` if `decision` is `"proposed"` (that's the initial state only, not a valid transition target).

**New**: `GET /contracts/{id}/versions` — list `ContractVersion` rows (`id`, `version_number`, `is_current`, `content_hash`, `created_at`) for the Versions tab.

**New**: `GET /search/global?q=&limit=` — tenant + public search across product surfaces, separate from `/search` (public Legal Knowledge Base only) so tenant data is never blended into a public-KB response without an explicit type label. Response: `{"query": "...", "results": [{"type": "CASE"|"CONTRACT"|"DOCUMENT"|"RESEARCH"|"LAW", "id": "...", "title": "...", "subtitle": "..."}]}`. `CASE`/`CONTRACT`/`DOCUMENT`/`RESEARCH` are ILIKE title/question matches scoped to `workspace_id`; `LAW` reuses the existing hybrid retriever against the public Legal Knowledge Base.

## Revision note — Phase 9.2 (Document Intelligence)

`POST /documents` is now a real, synchronous, end-to-end pipeline — upload → validate (size/magic-bytes/extension-MIME-mismatch/ZIP-bomb) → store (tenant/document-id-scoped path) → extract → normalize → detect structure → chunk → hash → embed/index — not merely a storage write. The response's `status` field reflects the real outcome (`ready`/`failed`/`ocr_required`/`unsupported`), never a fabricated success. `400` on validation failure with a machine-readable code prefix (e.g. `MIME_MISMATCH: ...`, `ZIP_BOMB_SUSPECTED: ...`).

**New**: `POST /documents/{id}/process` — explicit (re-)run of the pipeline; idempotent (old chunks are deleted before new ones are inserted), the documented retry path after a `failed` upload.

**Implemented**: `GET /documents/{id}/text` — previously a stub `501`; now returns `{document_id, text}` for a `ready` document, `409` otherwise (with the current status and `processing_error` in the message).

**New**: `POST /documents/{id}/ask` — `{"question": "..."}` -> `{status, answer, citations}`. `status` is `"answered"` or `"insufficient_document_evidence"` — the latter whenever tenant-document retrieval finds nothing OR the LLM itself doesn't self-report sufficient grounding; the endpoint never falls back to the model's general knowledge. Citations are `DOCUMENT_EVIDENCE` (page/clause into the tenant's own document), never formatted like a law citation.

**New**: `POST /documents/{id}/analyze` — provenance-tagged extraction: `extracted_dates`/`extracted_amounts`/`extracted_parties` (deterministic regex, each with a `provenance` pointing at the source page/clause) plus `inferred_obligations`/`inferred_risks`/`inferred_missing_information` (LLM-grounded, empty under `LLM_PROVIDER=mock`, never fabricated).

**New**: `DELETE /documents/{id}` — `204`; cascades to the document's chunks and deletes the stored file. Same workspace-scoped 404 semantics as every other tenant resource.

**Changed**: `POST /contracts` with `document_id` no longer `501`s — it reads `Document.extracted_text` from a `ready` document (real Document Intelligence → Contract Intelligence integration); `409` if the document isn't `ready` yet.

**Changed**: `POST /research` gained an optional `document_ids: list[uuid]` field — when present, each id is verified to belong to the caller's workspace (`404` otherwise), then relevant chunks are retrieved and injected into the research context, explicitly labeled as user-provided document evidence (never blended with, or cited as, legal authority).
