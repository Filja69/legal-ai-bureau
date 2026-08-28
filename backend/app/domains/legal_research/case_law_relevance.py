"""Case-Law Relevance (P2 §7). Keyword retrieval + citation validation only
prove a court decision EXISTS and is real — they say nothing about whether
it actually bears on the question at hand. This module is the missing
"does this citation matter" step, run only on evidence that has ALREADY
passed CitationValidator (VERIFIED or MOCK) — never on evidence whose
existence itself hasn't been confirmed, and never a place a fabricated
citation could sneak back in.

Deterministic factors (court level, recency) come straight from the
already-resolved `CourtDecision`/`Court` rows. The genuinely judgment-call
dimensions — factual similarity, legal-issue similarity, procedural
posture, and whether the decision supports or cuts against the theory —
require characterizing two texts against each other, which is exactly what
an LLM narrative pass is for; under LLM_PROVIDER=mock this degrades to an
honest "not assessed" rather than a fabricated judgment (see
`_UNASSESSED_STANCE`). The assessment is always presented as an AI
characterization of already-verified content, never as an added, unverified
citation of its own.
"""
from __future__ import annotations

import structlog

from app.domains.legal_research.models import AuthorityLevel, CaseLawRelevance
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, LLMStructuredGenerationError, TaskClass
from app.models.case_law import CourtDecision

logger = structlog.get_logger(__name__)

_RELEVANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "factual_similarity": {"type": "string", "enum": ["high", "medium", "low"]},
        "legal_issue_similarity": {"type": "string", "enum": ["high", "medium", "low"]},
        "procedural_posture_note": {"type": "string"},
        "stance": {"type": "string", "enum": ["supports", "against", "distinguishable", "unclear"]},
        "distinguishing_facts": {"type": "array", "items": {"type": "string"}},
        "remains_useful": {"type": "boolean"},
    },
}

_SYSTEM_PROMPT = (
    "You compare a retrieved, already-verified Russian court decision against a legal issue and case facts. "
    "You are NOT deciding whether the decision exists or is authentic — that has already been confirmed "
    "independently. Your only job is characterizing HOW relevant it is: factual similarity, legal-issue "
    "similarity, procedural posture, whether it supports or cuts against the theory being examined, and any "
    "material facts that would distinguish this decision from the case at hand. Never invent facts about the "
    "decision beyond what's given. If the decision text gives too little to judge a dimension, say so rather "
    "than guessing. Respond via the schema.\n\n" + UNTRUSTED_CONTENT_NOTICE
)

_UNASSESSED = "Оценка релевантности недоступна (LLM в mock-режиме или сбой генерации) — решение подтверждено, но не охарактеризовано."

_AUTHORITY_TO_COURT_LABEL = {
    AuthorityLevel.SUPREME_COURT: "Верховный Суд РФ",
    AuthorityLevel.CASSATION: "Кассационная инстанция",
    AuthorityLevel.APPEAL: "Апелляционная инстанция",
    AuthorityLevel.FIRST_INSTANCE: "Суд первой инстанции",
}


async def assess_case_law_relevance(
    llm_gateway: LLMGateway,
    *,
    decision: CourtDecision,
    authority: AuthorityLevel | None,
    issue_title: str,
    case_facts: list[str],
) -> CaseLawRelevance:
    court_label = _AUTHORITY_TO_COURT_LABEL.get(authority, "Суд") if authority else "Суд"
    decision_text = " ".join(filter(None, [decision.claim_summary, decision.decision_summary, decision.legal_reasoning]))

    prompt = (
        f"{wrap_untrusted('legal_issue', issue_title)}\n"
        f"{wrap_untrusted('case_facts', str(case_facts) if case_facts else '(none stated)')}\n"
        f"{wrap_untrusted('retrieved_decision', decision_text or '(no text available)')}"
    )
    # A strict enum-constrained schema is deliberately kept (over accepting
    # free text and coercing it) because it materially increases the odds a
    # real provider's output is actually one of the intended categories
    # rather than a near-miss synonym — but that means a mock/degenerate
    # response (e.g. every field empty) can fail schema validation and raise
    # after retries. That must degrade this one relevance assessment to
    # "unassessed", never propagate and break the theory/report it feeds.
    try:
        raw = await llm_gateway.structured_generate(
            TaskClass.REASONING, [LLMMessage(role="user", content=prompt)], response_schema=_RELEVANCE_SCHEMA, system=_SYSTEM_PROMPT
        )
    except LLMStructuredGenerationError as exc:
        logger.warning("case_law_relevance_generation_failed", case_number=decision.case_number, error=str(exc))
        raw = None

    if not raw:
        return CaseLawRelevance(
            case_number=decision.case_number, court_level_label=court_label, decision_date=decision.decision_date,
            outcome=decision.outcome, factual_similarity="unassessed", legal_issue_similarity="unassessed",
            procedural_posture_note=_UNASSESSED, stance="unassessed", assessed=False,
        )

    return CaseLawRelevance(
        case_number=decision.case_number,
        court_level_label=court_label,
        decision_date=decision.decision_date,
        outcome=decision.outcome,
        factual_similarity=raw.get("factual_similarity") or "unassessed",
        legal_issue_similarity=raw.get("legal_issue_similarity") or "unassessed",
        procedural_posture_note=raw.get("procedural_posture_note") or "",
        stance=raw.get("stance") or "unclear",
        distinguishing_facts=[f for f in raw.get("distinguishing_facts") or [] if isinstance(f, str) and f.strip()],
        remains_useful=bool(raw.get("remains_useful", True)),
        assessed=True,
    )
