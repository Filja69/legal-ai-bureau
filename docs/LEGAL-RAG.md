# LEGAL AI BUREAU — Retrieval Architecture

Principle: retrieval is never pure vector similarity. Legal text is precise (an article number is not "semantically close" to a neighboring one) — embeddings alone systematically fail exact citation and temporal queries. Six retrieval modes, composed by a router, not a single "search()" call.

## 1. Retrieval types

### Semantic Retrieval
Vector similarity (pgvector) over `EmbeddingChunk`, scoped by `jurisdiction` and optionally `code_type`. Used for "what does the law say about X" style questions where the user doesn't know the exact article.

### Exact Retrieval
Structured lookup, no embeddings: article number, clause, law title, case number, court, INN, contract number. Implemented as parameterized SQL against `Article`/`CourtDecision`/`CompanyProfile` — this path must never hallucinate, because it's a database read, not a generation.

### Citation Retrieval
Resolves a citation string (`"ГК РФ, статья 309"`) to a `Citation` record with full metadata (title, article, redaction, date, source, URL) — backs the clickable-citation UI (brief §27).

### Temporal Retrieval
Given `(code, article, event_date)`, returns the `Article`/`Clause` version whose `[effective_from, effective_to)` window contains `event_date`, plus the `Amendment` chain that produced it. See [LEGAL-DATABASE.md](LEGAL-DATABASE.md) §3.

### Case Retrieval
Hybrid semantic + metadata search over `CourtDecision`, filtered by court level, date range, article citations, outcome. Returns ranked results with the similarity breakdown in §3 below — never a bare relevance score.

### Hybrid Retrieval (default for open questions)
```
BM25 (Postgres tsvector / ts_rank, or external search index)
  +
Vector Search (pgvector cosine)
  +
Metadata filtering (jurisdiction, code_type, date range, court level)
  +
Reranking (cross-encoder or LLM-based rerank on top-K candidates)
```
This is the default path for Research Agent free-text queries; Exact/Citation/Temporal are invoked directly when the query has a recognizable structured target (regex/NER detects an article reference, case number, INN, etc. before falling back to hybrid).

## 2. Retrieval router

```python
def route_query(query: str, context: QueryContext) -> RetrievalPlan:
    if extract_citation(query):      return citation_plan(...)
    if extract_case_number(query):   return exact_case_plan(...)
    if context.event_date:           return temporal_plan(...)
    if context.intent == "case_law": return case_law_plan(...)
    return hybrid_plan(...)
```
Lives in `backend/app/rag/retrieval/`. Each `*_plan` returns a list of candidate `LegalDocument`/`Article`/`CourtDecision` ids with per-candidate provenance (which retrieval mode surfaced it, and its raw score) — this provenance is what the Citation Validator checks against.

## 3. Case similarity scoring (brief §19)

```json
{
  "fact_similarity": 0.92,
  "legal_similarity": 0.87,
  "contract_similarity": 0.81,
  "procedural_similarity": 0.74,
  "court_level_match": true,
  "date_relevance": 0.65,
  "overall_similarity": 0.83
}
```
Explicitly labeled and surfaced as **similarity score**, never as a win-probability estimate — the Litigation Agent's UI copy and the API response schema both forbid the phrase "chance of winning" anywhere near this number (brief §19).

## 4. Anti-hallucination system (brief §28)

Before any answer reaches the user, the **Citation Validator** runs against every citation the agents produced:

```python
class CitationValidator:
    async def validate(self, citation: CitationDraft) -> CitationCheck:
        # 1. Does the law/article/case exist in the Knowledge Base?
        # 2. Does the quoted fragment actually appear in the source content (exact or near-exact match)?
        # 3. Is the norm in force on the relevant event_date (temporal check)?
        # 4. If a case: does the case number/court/date resolve to a real CourtDecision row?
        ...
```

Outcomes:
- `verified` — passes all checks, rendered as a normal citation.
- `unverified` — retrieval found no matching source, or the quote doesn't match; rendered as `UNVERIFIED` and the associated conclusion is **downgraded to `confidence: low`**, never presented as settled fact. This is a hard gate in the Orchestrator's merge step (LEGAL-AGENTS.md §8), not a UI cosmetic — an agent cannot mark `escalate_to_human: false` while carrying unverified citations on a `high`/`critical` risk item.

This is what prevents the system from doing what a bare LLM does: inventing a plausible-sounding article number or case citation.

## 5. Confidence system (brief §29)

```json
{ "confidence": "high", "basis": "Основано на действующей норме ГК РФ и нескольких релевантных судебных актах." }
```

Confidence is computed, not asserted by the LLM:
- `high` — verified citation(s) to currently-effective norm + ≥1 verified, factually-similar (>0.75 overall_similarity) case, no contradicting `LegalPosition`.
- `medium` — verified norm citation but case law thin/absent, or minor contradiction present.
- `low` — any unverified citation on the load-bearing claim, or conflicting case law with no majority position (see §6).

## 6. Conflicting case law (brief §55)

The system never silently picks a side. When Case Retrieval surfaces materially conflicting `LegalPosition` rows:

```
Практика неоднородна.
Позиция A: ... (cases, courts)
Позиция B: ... (cases, courts)
Верховный Суд: ... (if a controlling position exists)
Наиболее сильная позиция: ...
Причина: ... (court level, recency, factual similarity — not recency alone, brief §54)
```

This structured disagreement is a first-class field in the `LegalResearchReport.analysis` — not something the frontend has to detect from prose. A conflict with no controlling Supreme Court position and no clear majority is itself an escalation trigger (PRD §9).

## 7. Source hierarchy (brief §53) — used to resolve conflicts, never to merge across types

```
1. Constitution
2. Federal constitutional laws
3. Federal laws / codes
4. Presidential acts
5. Government acts
6. Ministerial regulations
7. Official explanations (Plenum, letters)
8. Supreme Court positions
9. Other court practice
10. Secondary sources
```
"Закон" (tiers 1–7) and "судебная практика" (tiers 8–9) are reasoned about separately and never blended into one score — case law interprets/applies law, it doesn't outrank it.

## 8. Court practice quality weighting (brief §54)

Case ranking considers `court.level`, `decision_date` recency, `fact_similarity`, and `jurisdiction` match jointly — a Supreme Court position from 2019 outranks a first-instance decision from 2025 on the same point unless the first-instance case sits on a materially different, more recent statutory basis (detected via the Temporal Retrieval check against the article it cites).

## 9. Phase 5 revision note

`EmbeddingChunk` gained `embedding_provider` + `embedding_model_version` (brief §21-22) — `PgVectorRetriever` now filters to the currently-configured provider/model before computing cosine distance, so a future embedding-model switch can never silently compare vectors from two incompatible models in one ranking. A quantitative retrieval benchmark (Recall@1/5/10, MRR, Citation Recall — `backend/tests/evals/legal_retrieval/test_benchmark.py`) now exists alongside the original pass/fail regression cases; see the Phase 5 report for the mock-embedding baseline numbers it captured.

## 10. Phase 6 revision note

`OpenAIEmbeddingProvider` (`app/rag/embeddings/openai_provider.py`) is now a real, batched, timeout/retry-bounded implementation of `EmbeddingProvider` — `get_embedding_provider()` builds it when `EMBEDDING_PROVIDER=openai`, and fails fast (never falls back to mock) if `OPENAI_API_KEY` is missing. It has not been exercised against a live OpenAI response this session (no API key available in this environment) — see the Phase 6 report. `PgVectorRetriever`'s namespace filter now reads the single persisted `embedding_namespace` column instead of comparing two columns. `HybridRetriever.retrieve()` emits a structured `hybrid_retrieval` log line per call (`keyword_latency_ms`, `vector_latency_ms`, `reranker_latency_ms`, `retrieval_latency_ms`, candidate counts) via the existing `app.core.logging` structlog setup — no parallel logging framework. `POST /api/v1/legal/search/debug` (Admin/Owner only) exposes per-leg candidates, fusion, timings, embedding identity, and citation validation for a query — retrieval mechanics only, never chain-of-thought (there is none to expose: this endpoint never calls an LLM). `LegalChunkIndexer.reindex_all()` + `POST /knowledge/reindex` bulk-reindex into whichever namespace the current config resolves to, with a `dry_run` mode; "activating" a namespace is changing `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL`, not a separate DB flag.

## 11. Phase 6.5 revision note — cost protection, atomic activation, smoke test

`OpenAIEmbeddingProvider` now throttles itself to `EMBEDDING_MAX_REQUESTS_PER_MINUTE` (default 500) via a fixed-interval wait between batch requests, independent of the SDK's own 429 backoff — a safety ceiling, not a billing system. `LegalChunkIndexer.reindex_all(max_documents=...)` rejects (raises `ReindexLimitExceeded`, checked *before* any embedding call) a batch larger than `EMBEDDING_MAX_DOCUMENTS_PER_REINDEX` (default 5000); `POST /knowledge/reindex` wires this in and returns HTTP 413 on the limit. `ReindexReport.ready_to_activate` is a new explicit gate (brief §6): true only when every chunk that exists elsewhere has a same-namespace counterpart with zero failures — a partially-reindexed namespace is never reported as safe to switch `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL` to. `python -m app.cli.embedding_smoke_test` (brief §4) verifies real provider connectivity/dimensions/namespace with one minimal request — it never writes to `embedding_chunks`, never indexes, never reindexes, and states plainly `OPENAI_API_KEY missing / REAL API TEST NOT RUN` rather than silently testing mock instead. `LegalConflictDetector._detect_jurisprudential_conflict` was N+1 (one `SELECT` per court decision) — batched into one `WHERE id IN (...)` query (brief §16 performance audit).

## 12. Phase 7 revision note — real structured generation, model-tier fix, prompt injection defense

`AnthropicProvider.structured_generate()` and `OpenAIProvider.structured_generate()` (`app/llm/providers/`) are real now — previously both raised `NotImplementedError` unconditionally, meaning the whole Research/Contract pipeline could not run against a real LLM at all, regardless of `LLM_PROVIDER`. Anthropic uses forced tool-use (a single tool whose `input_schema` is the caller's `response_schema`, `tool_choice` pinned to it); OpenAI uses native `response_format={"type": "json_schema", ...}` (non-strict, since callers' schemas don't set `additionalProperties: false`). Schema *validation* (via `jsonschema`) and repair/retry (via a corrective follow-up message, `LLM_MAX_RETRIES` attempts, `LLM_TIMEOUT_SECONDS` per attempt) now live once, in `LLMGateway.structured_generate()` — shared across both providers rather than duplicated. Exhausting retries raises `LLMStructuredGenerationError`; the caller never receives a schema-invalid or partially-repaired dict.

**Real bug found and fixed in the process**: `LLMGateway`'s task-class → model routing table held placeholder tier names (`"strong"`, `"strongest"`, etc.) that were passed straight through as the literal `model=` string to the provider — harmless under `MockLLMProvider` (ignores the value), but would have been rejected outright by the Anthropic/OpenAI API as an unrecognized model the first time a real provider was ever used. Fixed via `_resolve_model(provider_name, tier)`, a per-provider tier → real-model-id table.

**`LLMGateway._build_provider()`** now fails fast (`LLMProviderError`) instead of silently returning `MockLLMProvider` when `LLM_PROVIDER=anthropic`/`openai` is set without the matching API key — mirrors `app/rag/embeddings/base.py::get_embedding_provider()`'s existing contract; this was a real pre-existing inconsistency (flagged, not fixed, in the Phase 6 report) closed here.

**Prompt injection defense** (`app/llm/prompt_safety.py`): every `_SYSTEM_PROMPT` across `app/domains/legal_research/` is a fixed module-level string literal (never built from a variable — verified by a static regression test), and every piece of untrusted content (user facts/questions, retrieved evidence text, issue titles) is passed through `wrap_untrusted(label, content)`, which fences it in `<untrusted_content label="...">` tags plus an explicit system-prompt-level instruction that delimited content is data, never a command. Regression-tested (`tests/unit/test_prompt_injection.py`) by capturing exactly what reaches the `system=` channel vs. the `user`-role channel for an injection-shaped payload (`"Ignore previous instructions..."`) — the payload never appears in `system=`, always inside the delimited block in user content. Note: this locks in the *structural* guarantee (injection can't reach the trusted channel); it cannot prove a real model would resist the injected instruction semantically, since no real LLM call was available to test against this session.
