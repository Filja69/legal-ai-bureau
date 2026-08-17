# Legal AI Assistant — routing shell, not a new backend

`frontend/features/dashboard/DashboardView.tsx` presents a single composer ("Чем помочь?") as the new home screen, per real first-user feedback: the previous Dashboard opened directly onto dense operational data (case/contract/research grids), which read as too complex before a first-time user had done anything.

**There is no universal-intent backend behind this composer.** No new endpoint, no LLM-based classifier, no orchestration layer was added. This document is the honest, explicit record of exactly what happens when a user interacts with it — required by the brief's "no fabrication" rule (§8) and stop condition (§12: "делать routing shell поверх существующих возможностей и явно это документировать").

## What actually happens

| User action | What happens | Why |
|---|---|---|
| Types free text, clicks "Отправить" (or Enter) | Client-side navigation to `/research?q=<text>`, which prefills the real Legal Research question box | `POST /research` is the one existing endpoint that genuinely accepts an arbitrary natural-language legal question — real fact extraction, retrieval, IRAC reasoning (see `docs/LEGAL-REALITY-MATRIX.md`). Reusing it is not fabrication; it's routing to the correct real feature. |
| Clicks "Прикрепить документ" | Client-side navigation to `/documents` | No cross-page file hand-off exists. Rather than build one just to feel smoother (itself a form of unnecessary scope per the brief), attaching a document *is* going to the real, working upload surface. Nothing is silently discarded — the composer never accepted a file to begin with. |
| Clicks "Проверить договор" | Navigates to `/contracts` | Real Contract Intelligence module (clause extraction, risk detection, two-lawyer review). |
| Clicks "Разобрать документы по делу" | Navigates to `/documents` | Real Document Intelligence upload/Q&A/analysis surface. |
| Clicks "Провести юридическое исследование" | Navigates to `/research` | Same real Legal Research Engine as the composer's text-submit path. |
| Clicks "Найти риски" | Navigates to `/contracts` | Contract risk detection lives inside Contract Intelligence — there is no standalone "risk finder" surface, so this is not a separate feature, just a second entry point into the same real module. |
| Clicks "Задать вопрос по документу" | Navigates to `/documents` | Document Q&A ("Ask" tab, evidence-gated) lives on a document's detail page; the list page is the real, honest entry point since there is no "pick a document to ask about" picker on the home screen. |

## What this explicitly is NOT

- Not a chat interface with memory or multi-turn conversation.
- Not an intent classifier — no text analysis happens client-side or server-side before routing; every action above is a fixed, hardcoded destination.
- Not capable of accepting "text + files together" as a single request — the two composer actions (send text / attach file) are independent, no combined submission exists.
- Not a replacement for Cases/Contracts/Documents/Research/Companies — those remain the real, full-featured surfaces; the Assistant only shortens the path to them for a first-time user.

## Next step if this is validated

If user testing confirms this routing shell earns its place, the next legitimate iteration is a real backend triage endpoint (e.g. classify free text into {contract review, document Q&A, research question} using the same deterministic-first principles as the rest of the project) — explicitly out of scope for this UX iteration per its own stop condition.
