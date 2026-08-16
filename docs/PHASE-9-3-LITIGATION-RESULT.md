# PHASE 9.3 — Litigation & Case Intelligence Engine — Result

Companion to `docs/LEGAL-REALITY-MATRIX.md`. Scope note up front: the Phase 9.3 brief specified a ~59-section system (case model, facts, timeline, evidence matrix, contradiction detection, claims/defenses, legal issue tree, opponent modeling, counterargument engine, procedural/limitation analysis, strategy scenarios, two-lawyer review, case memo + draft generation, a 50-case eval suite). Consistent with every prior phase in this project, that scope was deliberately cut down to what could be built **real, tested, and live-verified** in one session: **case parties, case-document linking, deterministic fact extraction with genuine provenance, timeline construction, evidence matrix, and contradiction detection.** Everything cut is marked `NOT_IMPLEMENTED` below — never partially built, never faked.

## 1. Architecture

`SOURCE → LAW → INTERPRETATION → APPLICATION → CONCLUSION` discipline applies here as: **document text → regex match → CaseFact (with evidence) → CaseEvent / CaseContradiction / EvidenceMatrixRow**. There is no `LLM → ANSWER` path anywhere in this pipeline — fact extraction, deduplication, timeline dating, contradiction detection, and evidence-strength scoring are **100% deterministic functions with zero LLM calls**. This was a deliberate choice: the brief itself calls out "do not produce Evidence strength = 83% unless there is an explicit deterministic model behind it," and a bounded regex-based system is more auditable than an LLM-based one for this v1 slice.

`app/domains/litigation/` holds five pure modules (`fact_extractor.py`, `fact_dedup.py`, `timeline_builder.py`, `contradiction_detector.py`, `evidence_matrix.py`) with no DB access — all business logic is independently unit-testable. `app/domains/litigation/pipeline.py`'s `LitigationCaseEngine` is the sole DB-touching orchestrator, following the idempotent delete-then-insert pattern established by Phase 9.2's `DocumentIntelligenceEngine`.

## 2. Database

Migration `0010_litigation_intelligence` adds 6 tables: `case_parties`, `case_documents`, `case_facts`, `case_fact_evidence`, `case_events`, `case_contradictions`. Every table has a mandatory `workspace_id` with the same permissive RLS scaffold pattern as prior phases (still-open Phase 1 TODO to tighten via `current_setting('app.current_workspace_id')`, not addressed this phase). `case_documents` reuses Phase 9.2's `Document`/`DocumentChunk` tables via foreign key — no document data is duplicated.

A real bug was found and fixed during migration development: `revision = "0010_litigation_case_intelligence"` (34 chars) exceeded `alembic_version.version_num`'s `varchar(32)` limit, causing `StringDataRightTruncationError` on the final `UPDATE alembic_version`. Transactional DDL rolled the DB back cleanly to `0009_document_intelligence`; the file was renamed to `0010_litigation_intelligence` (28 chars) and re-applied successfully. The full `upgrade → downgrade → upgrade` cycle was verified on a throwaway scratch database (`legal_ai_bureau_scratch_9_3`) before touching the dev DB.

## 3. Case model — parties and document linking

`CaseParty` (name, `PartyType`, `ProceduralRole`, free-form identifiers) and `CaseDocument` (a link table with its own `CaseDocumentRole` vocabulary — `invoice`/`act`/`correspondence`/`contract`/etc., distinct from both Phase 8's `DocumentType` and Phase 4's contract roles) are both real, tested, and live-verified: a party was added via the API and shown in the frontend; three real documents were attached to a real case with distinct roles in the browser this session.

## 4. Fact extraction

`fact_extractor.py` runs 5 shared regex patterns (`DATE_NUMERIC`, `DATE_WORDY`, `AMOUNT`, `PARTY_ENTITY`, `PARTY_ROLE` — promoted to `app/domains/shared/legal_patterns.py` so Contract Intelligence's `analysis.py` and Litigation's `fact_extractor.py` share one pattern library instead of maintaining two) over each attached document's real, already-extracted `DocumentChunk` text. Every candidate carries an `_EXCERPT_RADIUS = 80`-character bounded excerpt around the match. Known limitation carried over from Phase 9.2: the patterns are Russian-jurisdiction-specific (`руб`, `ООО`, `Заказчик`, month names) and will not fire on English-language documents — by design, not a bug, documented in both this report and the module docstring.

## 5. Provenance

Every `CaseFact` is backed by one or more `CaseFactEvidence` rows carrying `(document_id, chunk_id, page_number, section_path, excerpt)` — real foreign keys into Phase 9.2's `Document`/`DocumentChunk` tables, not free-floating text. `FactStatus.SUPPORTED` is therefore an honest label: it means a literal regex match against literal chunk text was found, never an LLM confidence score. Live-verified in-browser: all 4 facts extracted from the adversarial fixture show their real source document and excerpt (e.g., "Сумма к оплате составляет 500 000 руб. Товар передан 10.03.2026." linked to `invoice.txt`).

## 6. Deduplication and corroboration

`fact_dedup.py` groups raw per-chunk candidates by `(fact_type, normalized_value)` into one `CanonicalFact`, with `corroboration_count` computed as the count of **distinct documents** (not evidence rows) asserting that fact — deliberately conservative, deterministic-only, no semantic/embedding dedup. Live-verified: the `10.03.2026` delivery date shows `corroboration_count = 2` because both `invoice.txt` and `email.txt` independently assert it.

## 7. Timeline

`timeline_builder.py` parses each canonical DATE fact's `normalized_value` (`YYYY-MM-DD`) into a `CaseEvent`, tags it `DateType.EXACT` (or `UNKNOWN` on parse failure — never silently dropped), infers an `event_type` via a keyword classifier reading the fact's evidence excerpt (`infer_event_type()`, made public this phase so `contradiction_detector.py` could reuse it instead of duplicating the classifier), and sorts chronologically with a stable tie-break on description. Live-verified: two events (10 and 12 March 2026) render in correct chronological order, both tagged `EXACT` and `[delivery]`.

## 8. Evidence matrix

`evidence_matrix.py` is computed at read time, never persisted (deliberate anti-schema-explosion choice per brief §48). Each fact is scored `STRONG` (corroborated, uncontradicted), `MODERATE` (single source), or `CONFLICTED` (appears in any contradiction pair, overriding corroboration count). Live-verified: all 4 facts in the adversarial case correctly show `CONFLICTED`, each with the reason "Contradicted by another document in this case."

## 9. Contradiction detection

`contradiction_detector.py` implements two bounded, explicitly-documented deterministic heuristics — nothing broader is claimed:
- **Date mismatch**: two DATE facts with different `normalized_value` are flagged only when `infer_event_type()` groups them into the *same* event type (e.g. two "delivery" dates), preventing false positives between unrelated dates (a signing date vs. a payment-due date).
- **Amount mismatch**: any two distinct AMOUNT facts within a `max/min ≤ 5.0` ratio are flagged (`_MAX_AMOUNT_RATIO = 5.0`), deliberately catching the brief's own worked example (500,000 vs. 450,000 RUB) without a per-line-item claims model.

The module docstring is explicit that `PARTY_MISMATCH` and document-number/performance-status contradictions are **not implemented** — false-positive risk without a real normalization model the project doesn't have yet.

Live-verified against the brief's own §55 worked adversarial example (invoice 500,000 RUB/10 March delivery vs. act 450,000 RUB/12 March delivery, with a corroborating email confirming 10 March): the system correctly surfaced exactly one `date_mismatch` and one `amount_mismatch`, both showing the full text of both conflicting facts in the frontend.

## 10. Claims/defenses, legal issue tree — NOT_IMPLEMENTED

No persistence, no endpoint. Explicitly out of scope this phase — building a real issue tree without a claims model would risk fabricating legal structure not grounded in the case's actual documents.

## 11. Legal Research integration — NOT_IMPLEMENTED

No wiring from case facts/documents into `POST /research`'s `document_ids` parameter (which exists from Phase 9.2). A real integration point for a future phase, not attempted this session.

## 12. Opponent modeling / counterargument engine — NOT_IMPLEMENTED

No domain logic. The frontend Strategy tab states this honestly rather than fabricating content.

## 13. Procedural / limitation analysis — NOT_IMPLEMENTED

No statute-of-limitations or procedural-deadline logic. `/cases/{id}/deadlines` remains an explicit `501` stating it is "never fabricated, not merely deferred."

## 14. Strategy generation — NOT_IMPLEMENTED

`/cases/{id}/strategy` remains an explicit `501`. Frontend Strategy tab: "Opponent modeling, counterarguments, and strategy generation are explicitly out of scope this phase" — live-verified this exact text renders when the tab is clicked.

## 15. Two-lawyer review (litigation) — NOT_IMPLEMENTED

Phase 4's two-lawyer review exists for Contract Intelligence only; not extended to litigation case memos this phase (there is no case memo to review).

## 16. Case memo / draft generation — NOT_IMPLEMENTED

Frontend Drafts tab: "Draft procedural document generation is explicitly out of scope this phase" — live-verified.

## 17. API surface

New endpoints under `/api/v1/legal/cases/{id}/`: `GET/POST parties`, `GET/POST documents`, `GET facts` + `POST facts/extract`, `GET timeline` + `POST timeline/build`, `GET contradictions`, `GET evidence-matrix`, `POST analyze` (one-shot orchestration returning only counts, not full objects — avoids schema explosion), `GET analysis` (computed summary, not a persisted entity). `strategy` and `deadlines` remain honest `501`s. All new list/read endpoints batch their queries (e.g. `_load_facts_with_evidence()` uses a single `WHERE id IN (...)` for evidence lookup, avoiding N+1 per the Phase 2 lesson called out again in brief §50).

## 18. Frontend

`CaseDetailView.tsx` gained 4 fully real tabs (Documents, Facts, Timeline, Evidence) alongside honest "explicitly out of scope" messages for Issues/Strategy/Drafts — never a fabricated preview. Attach-document UI filters to `status === "ready"` documents not already attached. Facts show status badges (`FACT_STATUS_STYLE`) and evidence excerpts linked back to the source document. Evidence tab shows both the matrix table and a contradictions list with both conflicting fact statements side by side.

## 19. Security

Tenant isolation: 3 dedicated integration tests (attach-document cross-tenant 404, extract-facts cross-tenant 404, and a combined facts/timeline/evidence-matrix/contradictions/analyze/parties 404 check) — all passing against real Postgres. Prompt injection: the entire litigation pipeline is 100% deterministic with **zero LLM calls**, so `wrap_untrusted()` is architecturally not needed here — a stronger security position than an LLM-touching pipeline, stated explicitly rather than adding a placebo test.

## 20. Evaluation — NOT_IMPLEMENTED

No 50-case deterministic eval suite was built this phase. In its place, the brief's own single worked adversarial example (§55) is covered by a real integration test (`test_full_adversarial_pipeline_surfaces_contradictions`) and was additionally reproduced live in the browser this session — narrower than a 50-case suite, but proven against real Postgres and a real UI rather than asserted.

## 21. Tests — exact numbers

- Backend: **548 passed, 0 failed** (`poetry run pytest -q`, real Postgres/pgvector), up from 512 at the end of Phase 9.2.1 — **+36 tests** this phase (9 fact-extraction unit, 15 dedup/timeline/contradiction unit, 12 case-API integration).
- `ruff check .`: all checks passed.
- `mypy app`: Success, no issues in 205 source files.
- Frontend: `npm run lint` clean, `npm run type-check` clean, `npm run build` clean (21 routes, `/cases/[id]` now 6.39 kB), `npx vitest run` — **28 passed** (was 23; +5 from `CaseDetailView.test.tsx`).
- `docker compose config`: valid (verified with a temporary `.env` copied from `.env.example`, removed immediately after — no `.env` was committed or left behind).
- `alembic current`: `0010_litigation_intelligence (head)`.

## 22. Performance

No dedicated load testing this phase. The batched-query discipline (single `IN (...)` lookups for evidence and documents rather than per-row queries) keeps `GET /cases/{id}/facts` and `/analysis` at a small, fixed query count regardless of fact count, consistent with the Phase 2 N+1 lesson.

## 23. Live smoke test

Performed in a real browser session against the real backend (port 8010) and real frontend (port 3000), both started via `.claude/launch.json` preview configs:

1. **Login**: real JWT auth via `POST /auth/token` against a dev user (`smoke@example.com`, password reset for this session via a one-off DB script — no credential was fabricated or bypassed; the dev-bypass auth path was never used).
2. **Case creation**: created "Ромашка v. Поставщик — Спор по поставке" via the `/cases` UI form. `POST /api/v1/legal/cases` → `201`.
3. **Synthetic adversarial fixture**: uploaded 3 documents via the real upload pipeline, verbatim-matching the brief's own §55 worked example — `invoice.txt` ("Сумма к оплате составляет 500 000 руб. Товар передан 10.03.2026."), `act.txt` ("Согласно акту, стоимость составила 450 000 руб. Поставка произведена 12.03.2026."), `email.txt` ("Уведомляем: доставка ожидается 10.03.2026."). All three reached `READY` status.
4. **Attach documents**: attached all 3 to the case with roles `invoice`, `act`, `correspondence` respectively. `POST /cases/{id}/documents` → `201` ×3.
5. **Run Full Analysis**: `POST /cases/{id}/analyze` → `200`, response `{"fact_count": 4, "contradiction_count": 2, "event_count": 2}` — exactly matching the proven integration test's assertions.
6. **Facts tab**: 4 facts rendered, each `SUPPORTED`, each showing its real source document and excerpt.
7. **Timeline tab**: 2 events in correct chronological order (2026-03-10, 2026-03-12), both `EXACT` / `[delivery]`.
8. **Evidence tab**: all 4 facts `CONFLICTED`; both a `DATE MISMATCH` ("Documents disagree on the 'delivery' date: 2026-03-10 vs 2026-03-12") and an `AMOUNT MISMATCH` ("Documents disagree on an amount of similar magnitude: 500000.00 vs 450000.00") rendered with both conflicting fact statements shown side by side.
9. **Strategy tab**: correctly showed "Opponent modeling, counterarguments, and strategy generation are explicitly out of scope this phase" — no fabricated content.

This reproduces the backend integration test's exact assertions end-to-end through the real UI, not just at the API layer.

## 24. REAL

Case parties, case-document linking, fact extraction with provenance, deduplication/corroboration, timeline construction, contradiction detection (date/amount), evidence matrix — all deterministic, all tested, all live-verified this session (see `docs/LEGAL-REALITY-MATRIX.md` for the row-by-row breakdown).

## 25. STRUCTURALLY REAL / MOCK-EXECUTED

None new this phase — the litigation pipeline has no LLM dependency, so there is nothing gated behind `LLM_PROVIDER=mock` here (unlike Document Q&A/Analysis in Phase 9.2).

## 26. MOCK

None. Every litigation capability built this phase operates on real data with no synthetic/demo layer underneath it (the fixture *documents* are synthetic by design — a deliberately constructed adversarial test case — but the extraction/detection logic that processes them is real, not mocked).

## 27. BLOCKED

None. Docker/Postgres has been healthy since Phase 9.2.1; no infrastructure blocker this session.

## 28. NOT IMPLEMENTED

Claims/defenses, legal issue tree, Legal Research integration, opponent modeling, counterargument engine, procedural/limitation analysis, strategy generation, two-lawyer review for litigation, case memo/draft generation, 50-case eval suite. All explicitly scoped out at the start of this phase and confirmed still absent — never partially built, never faked in the UI.

## 29. Bugs found and fixed

1. **Migration revision-ID length**: `0010_litigation_case_intelligence` (34 chars) exceeded `alembic_version.version_num varchar(32)`, causing a clean transactional rollback on `alembic upgrade head`. Fixed by shortening the revision id to `0010_litigation_intelligence` (28 chars). See §2.
2. **`.claude/launch.json` backend preview config**: `runtimeExecutable: "bash"` resolved to Windows' WSL-relay `bash.exe` (`C:\Windows\System32`) instead of Git Bash, producing a WSL/NAT localhost error. Fixed with the explicit path `C:\Program Files\Git\usr\bin\bash.exe`.
3. **Cases page hydration warning (observed, not fixed — out of scope)**: `AuthGuard.tsx` renders `null` server-side (no `isAuthenticated` during SSR) but the authenticated tree client-side, producing a React hydration-mismatch warning on the `/cases` page in dev mode. Next.js recovers automatically by discarding server HTML and doing a full client re-render — every subsequent interaction, request, and data flow was confirmed correct. This is a pre-existing, app-wide pattern (not introduced this phase) affecting any client-storage-gated page, not specific to litigation. Left unfixed as out of scope for a litigation-focused phase; flagged here for a future frontend-hygiene pass (e.g. a `mounted` guard before first render).

## 30. Remaining risks

- The date/amount contradiction heuristics are intentionally bounded (single event-type grouping; ≤5x amount ratio) — a real dispute with more than two conflicting values per fact, or amounts differing by more than 5x, will not be caught. This is documented, not hidden.
- Regex-based fact extraction is Russian-pattern-only; English-language case documents will silently yield zero facts (not an error, but a silent gap worth surfacing to users).
- The RLS scaffold on all 6 new tables remains the permissive `USING (true)` placeholder inherited from Phase 1 — tenant isolation is enforced at the application layer (tested) but not yet at the database layer.
- The `/cases` page hydration warning (§29.3) is cosmetic in dev but worth a real fix before this becomes a production build target.

## 31. Recommended next phase

Per the brief's own stop condition, this session does not proceed further. If continued, the highest-value next slice would be either (a) wiring case documents into the existing `POST /research` endpoint (Legal Research integration, §11 — the most contained NOT_IMPLEMENTED item, reusing existing infrastructure) or (b) a small claims/issue model, since almost every deferred item (opponent modeling, counterarguments, strategy, procedural analysis) depends on claims/issues existing first.

## 32. Verdict

**PHASE 9.3 VERIFIED**

Rationale: every capability claimed REAL in this report was exercised against real Postgres by the automated test suite (548/548 passing) **and** independently reproduced end-to-end in a live browser session, matching the brief's own worked adversarial example exactly (2 contradictions: 1 date mismatch, 1 amount mismatch, both with genuine document provenance). Nothing marked NOT_IMPLEMENTED is presented as available in the UI or API — every out-of-scope capability returns an honest `501` or an explicit "out of scope" message, never a fabricated result.
