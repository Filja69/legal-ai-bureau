# LEGAL AI BUREAU — Product Requirements Document

## 1. Product statement

Legal AI Bureau (product name; agent name **Legal Agent**) is an AI Legal Intelligence Platform — not a chatbot with a legal system prompt. It approximates a working legal bureau: it researches law, verifies its own sources, analyzes and drafts documents, checks counterparties, builds litigation strategy, and tells the user explicitly when a human lawyer is required.

Core philosophy (non-negotiable, drives every architectural decision downstream):

- AI does not replace the source of law.
- AI does not invent law.
- AI researches law, verifies sources, analyzes facts, builds argumentation, and supports — not replaces — legal decision-making.

Architecture principle: `SOURCE → LAW → INTERPRETATION → APPLICATION → CONCLUSION`, never `LLM → ANSWER`. See [LEGAL-ARCHITECTURE.md](LEGAL-ARCHITECTURE.md).

## 2. Relationship to Jarvis

Legal AI Bureau is built and shipped as an **independent product** with its own repo (`E:\Проекты\legal-ai-bureau`), own database, own auth, own frontend. It is not a module bolted onto the existing `jarvis` monorepo's `agents/legal-agent` (audited and left untouched — see [LEGAL-ROADMAP.md](LEGAL-ROADMAP.md) Phase 0 notes).

It exposes a stable HTTP API (see [LEGAL-API.md](LEGAL-API.md)) so Jarvis — or any other orchestrator — can call it as a specialized agent:

```json
{ "task": "analyze_contract", "document_id": "...", "jurisdiction": "RU" }
```

and receive a structured result. Integration is Phase 7 work, after the standalone product is stable (section 50/65 of the source brief).

## 3. Jurisdiction scope

- **Primary market at launch: Russian Federation.** All initial law/case-law sources, retrieval logic, document templates, and deadline calculations target RU law.
- Architecture is jurisdiction-extensible from day one (`Jurisdiction` entity, `jurisdiction` field on every legal document, workspace, and query) — adding EU/US/other jurisdictions later must not require schema or pipeline rewrites.
- Norms from different jurisdictions are never mixed in a single retrieval or reasoning pass.
- Workspace defaults: `jurisdiction=RU`, `language=ru`.

## 4. Primary users

| Role | Need |
|---|---|
| Business owner / exec (e.g. Jarvis's own user profile — founder handling own contracts) | Fast contract review, risk visibility, drafting without hiring counsel for routine matters |
| In-house / retained lawyer | Research acceleration, first-draft generation, due diligence automation, litigation prep |
| Paralegal / analyst | Document processing, evidence organization, deadline tracking |
| Client (read-only) | Visibility into case status and documents shared with them |

## 5. Product surfaces (chat is secondary — section 49 of brief)

Six primary products, all backed by the same knowledge/agent core:

1. **Contract Intelligence** — upload, parse, risk-score, redline, generate contracts
2. **Legal Research** — question → sourced legal analysis with case law
3. **Litigation Intelligence** — case strategy, evidence matrix, argument building
4. **Due Diligence** — counterparty/company legal risk profile
5. **Corporate Legal** — entity, governance, protocol/decision management
6. **Document Generation** — structured drafting with mandatory Draft→Review→Risk pipeline

**Legal Chat** is a universal entry point that routes into these five products via the Legal Orchestrator (see [LEGAL-AGENTS.md](LEGAL-AGENTS.md)) — it is not itself the product.

### Revision note — Phase 8 actually-shipped product surfaces

The six-surface v1 sketch above diverged from what was actually built, as each phase narrowed scope to what had a real backend behind it (LEGAL-ROADMAP.md §Phase 8). What shipped as a real, workspace-scoped frontend surface:

- **Dashboard** — aggregated view over real Cases/Contracts/Research (action items: contracts awaiting analysis, low-confidence or escalated research); no fabricated stats
- **Cases** (list + detail) — real CRUD; Overview and Research tabs are real, Facts/Evidence Matrix/Deadlines tabs honestly show "not implemented" (backing endpoints are genuine `501`s) rather than empty/fake data
- **Contract Intelligence** — Overview/Clauses/Risks/Redline/Versions tabs, all real; Redline requires an explicit human Accept/Reject per change (the AI never applies a change itself)
- **Legal Research** — question → sourced analysis, now with a persisted history list and a reload-by-id detail view (was compute-and-discard through Phase 7)
- **Documents** — upload + list; text extraction stays explicitly unavailable (`501`), never a fabricated "processing" status
- **Knowledge admin** — Sources/Index/Search Debug, admin/owner-only, reusing the existing `/knowledge/*` and `/search/debug` endpoints rather than a second debug engine
- **Settings** — profile/workspace/security, backed by `GET /auth/me`
- **Global Search** — tenant (Case/Contract/Document/Research) + public Legal Knowledge Base, results always type-labeled, never blended silently

**Not built** (honestly unavailable, not faked): **Companies/Due Diligence** (backend `/companies` and `/due-diligence` are `501` — no real data provider connected) and **Litigation Intelligence**/**Document Generation** as standalone surfaces (their backend endpoints don't exist yet — see LEGAL-ROADMAP.md Phase 5/6 candidates). **Legal Chat** was deprioritized in favor of the direct product surfaces above; its route still exists but is not linked from the primary navigation.

## 6. Critical, cross-cutting requirements

- **No fact without a source.** Every material legal conclusion must carry: source, exact norm, redaction/date, source URL, quoted fragment, applicability rationale, confidence level. Unverifiable claims render as `UNVERIFIED`, never as fact. See [LEGAL-RAG.md](LEGAL-RAG.md) §Anti-Hallucination.
- **Temporal correctness.** Every norm/case has a validity window; queries can be pinned to an `event_date` so results reflect law as it stood on that date, not today. See [LEGAL-DATABASE.md](LEGAL-DATABASE.md) §Versioning.
- **Two-lawyer principle.** For any generated/analyzed document of consequence: Draft → independent Review → Risk pass → Orchestrator merge. No single LLM call self-certifies its own output. See [LEGAL-AGENTS.md](LEGAL-AGENTS.md) §Draft-Review-Correction.
- **Human escalation.** High risk, large sums, litigation, criminal matters, complex corporate disputes, insufficient facts, or contradictory case law must trigger an explicit "Human Legal Review" recommendation with a case packet handed to a human lawyer. See §11 below.
- **Confidentiality.** No client document, case fact, or workspace content is ever used to train or fine-tune a model, or leaks into the shared public knowledge base. See [LEGAL-SECURITY.md](LEGAL-SECURITY.md).

## 7. Non-goals (v1)

- Not a substitute for licensed representation in court or before regulators — the product surfaces this explicitly, without an oversized disclaimer banner (see §10).
- Not a scraper of paywalled commercial legal databases (КонсультантПлюс/ГАРАНТ) — those are integrated only via licensed/official APIs or user-supplied exports; the connector interface ships with a mock implementation until such an agreement exists.
- Not a general-purpose chatbot — every answer that makes a legal claim must go through the reasoning pipeline, not a bare LLM completion.
- Not multi-jurisdiction at launch — extensibility is architected, RU is the only populated jurisdiction initially.
- Billing/monetization tiers (Free/Starter/Pro/Business/Bureau/Enterprise) are modeled in the schema but not implemented/enforced in v1.

## 8. Success criteria (ties to AI evaluation, see LEGAL-ROADMAP §Testing)

A user should be able to say, truthfully, after using the product:

- "I uploaded a contract — it actually analyzed it, clause by clause."
- "I asked a legal question — it did research, not guessing."
- "It showed me where every material conclusion came from."
- "It found relevant case law."
- "It caught risks I would have missed."
- "It produced a corrected draft."
- "It told me plainly where it wasn't sure, and where I need a real lawyer."

Measured via: citation accuracy, source accuracy, retrieval recall, hallucination rate, issue-identification accuracy, contract risk-detection accuracy, temporal accuracy, case-similarity quality (see [LEGAL-ROADMAP.md](LEGAL-ROADMAP.md) §AI Evaluation).

## 9. Disclaimer & escalation UX (section 30–31 of brief)

Disclaimer is factual, not alarmist, surfaced contextually (e.g. footer of every generated legal opinion/document, not a modal):

> AI предоставляет информационную и аналитическую поддержку и не заменяет квалифицированного юриста/адвоката там, где требуется профессиональное юридическое представительство или иная лицензируемая деятельность.

Escalation triggers (any one is sufficient) surface a "Human Legal Review Recommended" panel with a pre-assembled packet (facts, documents, research, risks, open questions, AI conclusion, sources):

- Risk Matrix severity = CRITICAL
- Amount in dispute above a configurable workspace threshold
- Active or imminent litigation / criminal exposure
- Complex corporate dispute (shareholder conflict, M&A)
- Case Retrieval returns contradictory case law with no clear majority position (see [LEGAL-RAG.md](LEGAL-RAG.md) §Conflicting Case Law)
- Fact Extraction cannot resolve enough critical unknowns for a confident conclusion
