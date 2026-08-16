"""Obligation/deadline/money-term extraction — brief §14-16.

Deterministic, regex/keyword-based — not LLM paraphrase. Every extracted
obligation traces back to a clause via `clause_id`, and `action` is a
verbatim excerpt of the clause text, never a rewritten summary, so nothing
here can silently drift from what the contract actually says.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.domains.contracts.structure_extractor import ExtractedClause
from app.models.contracts import ClauseType

_PARTY_KEYWORDS = [
    "Заказчик", "Исполнитель", "Поставщик", "Покупатель", "Арендатор", "Арендодатель",
    "Лицензиат", "Лицензиар", "Работодатель", "Работник", "Сторона",
]

_DEADLINE_PATTERN = re.compile(
    r"\b(?:в течение\s+)?(\d+)\s*"
    r"(рабочих|календарных|банковских)?\s*"
    r"(дн\w*|месяц\w*|недел\w*|час\w*)\b",
    re.IGNORECASE,
)

_OBLIGATION_TYPE_BY_CLAUSE_TYPE = {
    ClauseType.PAYMENT: "payment",
    ClauseType.DELIVERY: "delivery",
    ClauseType.NOTICE: "notice",
    ClauseType.RENEWAL: "renewal",
    ClauseType.TERMINATION: "termination",
    ClauseType.WARRANTY: "warranty",
    ClauseType.ACCEPTANCE: "claim",
}


@dataclass
class ExtractedObligation:
    clause_index: int  # index into the ExtractedClause list this came from
    party: str | None
    action: str
    deadline: str | None
    obligation_type: str | None


def extract_obligations(clauses: list[ExtractedClause]) -> list[ExtractedObligation]:
    obligations: list[ExtractedObligation] = []
    for idx, clause in enumerate(clauses):
        obligation_type = _OBLIGATION_TYPE_BY_CLAUSE_TYPE.get(clause.clause_type)
        if obligation_type is None:
            continue

        party = next((p for p in _PARTY_KEYWORDS if p in clause.normalized_text), None)
        deadline_match = _DEADLINE_PATTERN.search(clause.normalized_text)
        deadline = deadline_match.group(0) if deadline_match else None

        obligations.append(
            ExtractedObligation(
                clause_index=idx,
                party=party,
                action=clause.normalized_text[:200],
                deadline=deadline,
                obligation_type=obligation_type,
            )
        )
    return obligations
