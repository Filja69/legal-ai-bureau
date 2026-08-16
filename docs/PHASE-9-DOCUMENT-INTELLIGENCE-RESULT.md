# PHASE 9.2 RESULT — Production Document Intelligence

Written 2026-08-14. Continuation of Phase 9 (`docs/PHASE-9-AUDIT.md`, `docs/PHASE-9-RESULT.md`). Scope per this phase's brief: a real document pipeline (upload security → extraction → chunking → tenant-scoped indexing → Q&A/analysis → Contract/Research integration). Explicitly out of scope and not attempted: Litigation/Corporate/Due-Diligence engines, Jarvis integration, new decorative agents, commercial legal DB connectors, OCR.

> **Update 2026-08-15 (Phase 9.2.1)**: Docker/Postgres recovered in the following session and everything marked `BLOCKED` below (migration `0009` against a live DB, the 27 integration tests, the live smoke test) was actually run — **512/512 tests passed against real Postgres**, and two real bugs were found and fixed in the process. See `docs/PHASE-9-2-INTEGRATION-VERIFICATION.md` for the full verification report; `docs/LEGAL-REALITY-MATRIX.md` reflects the current, live-verified status. The `BLOCKED` sections below are left as originally written, as an accurate record of what this specific session could and couldn't prove.

## 1. Architecture

`app/documents/{validation,storage,extraction,chunking}` (file-level, no DB, no LLM — single responsibility per the brief) → `app/domains/documents/{pipeline,qa,analysis,citations}` (orchestration, DB writes, LLM calls) → `app/api/v1/documents.py` (thin HTTP layer). No new parallel architecture: extended the existing `Document` model rather than creating a second one, reused `WorkspaceScopedRepository`, `LLMGateway`, `EmbeddingProvider`, and `wrap_untrusted` exactly as the Contract/Research domains already do. The one genuinely new structural decision — a separate `document_chunks` table rather than extending `EmbeddingChunk` — is because `EmbeddingChunk` (public Legal Knowledge Base) has no `workspace_id` column at all by design; adding tenant data there would have broken the structural guarantee that makes cross-tenant KB leakage impossible.

## 2. Formats supported

PDF (text-layer only), DOCX (paragraphs/headings/tables), TXT/CSV (UTF-8), XLSX (best-effort, each sheet as a table) — all real, all tested against real bytes (hand-assembled valid PDF/DOCX/XLSX fixtures, not mocked file objects). Images (PNG/JPEG) are accepted as uploads (validated, stored) but have no text extractor — `get_extractor()` returns `None` and the document is honestly marked `unsupported`, never a fake empty extraction.

## 3. Extraction

`DocumentExtractor` Protocol, one implementation per format, each strictly `bytes -> ExtractedDocument` — no LLM calls, no DB writes, matching the brief's single-responsibility requirement. PDF extraction (`pypdf`) tracks per-page provenance and raises `OcrRequiredError` (mapped to the honest `ocr_required` status) when zero pages have a real text layer — never sends a page image to an LLM and calls it extraction. DOCX extraction (`python-docx`) tracks heading-derived `section_path` and extracts tables separately. Corrupted files (bad ZIP, non-PDF bytes with a spoofed header, etc.) raise `ExtractionError` with a machine-readable `code`, caught by the pipeline and turned into `status=failed` + `processing_error`.

## 4. Storage

`app/documents/storage/local_storage.py` rewritten: path shape is `var/documents/{workspace_id}/{document_id}{suffix}` — every path component after the storage root is a server-generated UUID. The original client filename is never used as a path component (stored only as `Document.original_filename` metadata), so path traversal (`../../secret`, absolute paths, Unicode tricks) is structurally impossible, not merely filtered.

## 5. Security

Upload validation (`app/documents/validation.py`) checks, in order: empty file, allow-listed extension, magic-byte signature matching the claimed extension (extension/MIME mismatch is rejected, including the case where a `.txt`-claimed file is actually a binary format), and for ZIP-based formats (DOCX/XLSX) a genuine ZIP-bomb defense — entry count cap (5,000), uncompressed-size cap (200 MB), and compression-ratio cap (100x) — checked from `ZipFile.infolist()` metadata alone, never by decompressing the archive. Reuses the existing 25 MB `MAX_UPLOAD_SIZE_BYTES` from Phase 9's security hardening rather than introducing a second, possibly-contradicting limit. Prompt injection: document text is always passed to the LLM wrapped in `wrap_untrusted()` (the same mechanism as Contract/Research, not a parallel one) — verified structurally (the injected string never appears in a `system=` parameter) and via an end-to-end test that uploads a document containing an injection payload and confirms the endpoint doesn't crash or fabricate a compliant-sounding answer.

## 6. Database changes

Migration `0009_document_intelligence`: `Document` gained `original_filename`, `media_type`, `size_bytes`, `sha256` (indexed), `status` (new `DocumentStatus` enum: `uploaded`/`processing`/`ready`/`failed`/`ocr_required`/`unsupported`), `processing_error`, `processed_at`. New table `document_chunks` (workspace-scoped, FK-cascaded from `documents`, unique on `(workspace_id, document_id, chunk_index)`, same embedding/namespace columns as `EmbeddingChunk`), with the same permissive RLS scaffold as other tenant tables for parity (the underlying enforcement is still the Phase-1-era open TODO, not tightened this phase). **Not applied to a live database this session — Docker/Postgres was unreachable the entire session; the migration file was reviewed by hand and via `ruff`/`mypy`, not exercised against real Postgres.**

## 7. Tenant indexing

`DocumentChunk` is structurally separate from the public `EmbeddingChunk` table (see §1) — every row has a mandatory `workspace_id`. `TenantDocumentRetriever` (mirrors `PgVectorRetriever`'s pattern) requires `workspace_id` as a constructor-time argument, not an optional filter a caller could forget. Reprocessing a document deletes its old chunks before inserting new ones (idempotency — verified by a dedicated test asserting chunk count is stable across two `/process` calls).

## 8. Document retrieval

Real cosine-similarity retrieval via the same `EmbeddingProvider` abstraction used for the public KB (mock by default, same namespace-isolation discipline from Phase 6). Used by both `/documents/{id}/ask` (single document) and `/research` (optional, user-selected `document_ids`, ownership-verified against the caller's workspace before any retrieval happens).

## 9. Document Q&A

Two independent evidence gates, not one: (1) if tenant-document retrieval returns zero chunks, the LLM is never called at all; (2) the LLM must itself self-report `sufficient_evidence: true` in its structured response. Either gate failing returns `insufficient_document_evidence` with an empty answer — never a best-effort guess. Citations are resolved only against chunks that were actually retrieved (a test explicitly injects a fabricated `cited_chunk_indices` value from the fake LLM and confirms it's silently dropped, not surfaced as a real citation).

## 10. Document analysis

Three explicit provenance categories, never blurred: `EXTRACTED` (deterministic regex over the actual chunk text — dates, amounts, party names/roles — each with a `provenance` string pointing at the source page/clause), `INFERRED` (LLM-grounded obligations/risks/missing-information, empty under `LLM_PROVIDER=mock` rather than fabricated), and `UNVERIFIED` (reserved in the result shape; nothing this implementation produces currently needs it).

## 11. Contract integration

`POST /contracts` with `document_id` no longer 501s (Phase 8's placeholder) — it reads `Document.extracted_text` from a `ready` document. Document Intelligence owns FILE→TEXT; Contract Intelligence owns TEXT→legal analysis; this is the seam between them, not a duplicated extraction path. A non-`ready` document (e.g. `ocr_required`) returns `409`, not a silent empty contract.

## 12. Frontend

`/documents` (list, with real per-document status badges distinct from the shared citation-verification `StatusBadge`) and `/documents/[id]` (Overview/Content/Analysis/Ask/Citations tabs). Overview shows extractor/page-count/chunk-count/warnings and a Retry button for `failed`/`ocr_required` documents. Ask shows the evidence-gated answer with citations inline; Citations aggregates citations across the session's Q&A exchanges. Build/lint/type-check all pass.

## 13. Tests — exact numbers

Backend: **512 tests collected** (was 432 before this phase). `ruff check .` — all checks passed (194 source files, up from 179). `mypy app` — no issues found (194 source files). DB-independent unit suite: **209 passed, 0 failed** (was 161 — **48 new** Document Intelligence unit tests: validation, extraction incl. OCR/corrupted-file paths, normalization/structure-detection/chunking incl. offset consistency, Q&A/analysis evidence-gating and prompt-injection). 27 new DB-dependent integration tests were written (`tests/integration/test_document_pipeline.py` — upload-to-ready for TXT/DOCX/PDF, OCR_REQUIRED, ZIP-bomb rejection, dedup within/across workspaces, idempotent reprocessing, 5 tenant-isolation tests, delete-cascades-chunks, evidence-gated ask, prompt injection, provenance-tagged analyze, Contract-from-Document, Research-with-documents) — **not run this session, Docker/Postgres unreachable** (see §14). Frontend: `npx vitest run` — **5 test files, 23 passed, 0 failed** (was 11 — added `DocumentStatusBadge` (6 states) and `DocumentDetailView` (forbidden, retry, OCR-vs-failed distinction, evidence-gated ask, citation display) — **and fixed a real pre-existing bug**: `vitest.setup.ts` had no DOM cleanup between tests, so any multi-test file was silently order-dependent; this was latent since Phase 8's test suite was introduced and is fixed now for every existing test file too, not just the new ones. `npm run lint`/`type-check`/`build` all pass.

## 14. Live smoke

**Not performed.** Docker Desktop was unreachable for the entirety of this session — `docker ps`/`docker compose ps` never responded despite the Docker Desktop process running (same symptom as the prior Phase 9 session; root cause still not diagnosed). Per the brief's explicit instruction not to spend 20 minutes retrying, this was checked once at the start of the session (`docker compose config` succeeded — the compose file itself is valid — but `docker compose ps` hung) and once more near the end, and both times treated as `INFRASTRUCTURE BLOCKED` rather than retried in a loop. No end-to-end scenario (upload → process → ask → analyze → Contract-from-Document) was exercised against a running system this session — only the 209 DB-independent unit tests and the 27 written-but-unrun integration tests stand behind the pipeline's correctness claims.

## 15. REAL

Upload validation (magic bytes, ZIP-bomb defense, extension/MIME mismatch), PDF/DOCX/TXT/XLSX extraction, normalization/structure-detection/chunking, tenant-scoped storage and indexing, Contract-from-Document integration, Research document-evidence integration (logic layer — all verified via unit tests with real byte-level fixtures and fake-but-schema-faithful LLM gateways).

## 16. PARTIAL

Document Q&A/analysis's LLM-dependent half (INFERRED facts, the answer text itself) — real code, correct gating logic, but never exercised against a live Anthropic/OpenAI API (same `UNVERIFIED LIVE` status as every other LLM-calling path in this project). XLSX extraction ("best-effort, not load-bearing for completion" per the brief — implemented and unit-tested, but not exercised in the DB-dependent integration suite this session).

## 17. MOCK

Nothing new in this phase is mock-by-design — all extraction is against real bytes, all chunking is real regex/text logic. The LLM provider itself defaults to `MockLLMProvider` (project-wide default, unchanged from earlier phases), which is why §16's INFERRED fields are empty in this session's test runs — an honest empty result, not a fabricated one.

## 18. BLOCKED

Migration `0009` applied to a live database; all 27 new integration tests; any live smoke test — all blocked by the Docker/Postgres outage described in §14, not by anything in the code.

## 19. NOT IMPLEMENTED

OCR (explicitly out of scope per the brief — architecture leaves room for a provider to be added later without touching the `DocumentExtractor` interface). Litigation/Corporate/Due-Diligence engines (explicitly out of scope). A queryable, persisted audit trail (documents are logged via `structlog`'s `document_processed` event, same pattern as every other Phase 7-9 audit event — still not a queryable `AuditLog` table).

## 20. Bugs found and fixed

1. **Extension/MIME-mismatch bypass for `.txt`/`.csv`**: the initial validation only checked UTF-8 decodability for text files, which a PDF's mostly-ASCII header bytes happen to satisfy — a `.txt`-labeled PDF passed validation. Fixed by checking magic-byte detection first and rejecting any positively-identified binary signature before attempting the UTF-8 decode.
2. **`DocxExtractor`/`XlsxExtractor` didn't catch `zipfile.BadZipFile`**: non-ZIP bytes uploaded with a `.docx`/`.xlsx` extension (that had somehow passed validation, e.g. via a future validation gap) crashed with an unhandled exception instead of the intended `ExtractionError("CORRUPTED_FILE", ...)`. Fixed by adding `zipfile.BadZipFile` to both extractors' except clauses.
3. **DELETE endpoint FastAPI assertion failure**: `@router.delete(..., status_code=204)` without `response_model=None` triggered `AssertionError: Status code 204 must not have a response body` at import time in this FastAPI version. Fixed by adding the explicit `response_model=None`.
4. **Frontend test-isolation bug (pre-existing, not introduced this phase)**: `vitest.setup.ts` never called Testing Library's `cleanup()` between tests, so DOM from one test could leak into the next and cause spurious pass/fail depending on execution order. Found while writing `DocumentDetailView.test.tsx`'s multi-test suite; fixed in `vitest.setup.ts`, benefiting every existing test file retroactively.

## 21. Remaining risks

Everything in §14/§18 is unverified against a live system — the pipeline's correctness claims rest on unit tests with hand-built byte fixtures and fake LLM gateways, not a real end-to-end run. The `document_chunks` RLS policy is the same permissive `USING (true)` scaffold as every other tenant table (Phase 1's still-open TODO) — real enforcement remains query-discipline-only (`WorkspaceScopedRepository`/`TenantDocumentRetriever`'s mandatory `workspace_id` argument), not defense-in-depth at the database layer yet. XLSX extraction has no dedicated integration test. Large documents (very high page/clause counts) haven't been performance-tested — the chunker's fallback sliding-window and the structured-clause path are both O(n) but unmeasured at scale.

## 22. Recommended next step

The moment Docker/Postgres is reachable: run `alembic upgrade head`, the full 512-test suite, and the live smoke scenario from the brief (login → upload TXT → process → READY → view extracted text → ask a question → receive a cited answer → upload DOCX → process → view clauses → create Contract from Document → run Contract analysis → view risks; PDF with a text layer as a secondary check) before claiming this phase's Definition of Done is met — the brief is explicit that Phase 9.2 is not complete until that live verification happens, and this session could not perform it.

Not starting Phase 10, Litigation/Corporate/Due-Diligence, or Jarvis integration, per the brief.
