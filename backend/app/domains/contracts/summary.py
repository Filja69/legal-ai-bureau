"""ContractSummary — brief §13. Generated purely from already-extracted
structured clauses (never a fresh LLM read of the whole contract), so it
can never say something the clause extraction didn't actually find.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domains.contracts.structure_extractor import ExtractedClause
from app.models.contracts import ClauseType

_SUMMARY_FIELDS: dict[str, ClauseType] = {
    "subject": ClauseType.SUBJECT,
    "price": ClauseType.PRICE,
    "payment_terms": ClauseType.PAYMENT,
    "term": ClauseType.TERM,
    "termination": ClauseType.TERMINATION,
    "liability": ClauseType.LIABILITY,
    "governing_law": ClauseType.GOVERNING_LAW,
    "dispute_resolution": ClauseType.DISPUTE_RESOLUTION,
    "ip": ClauseType.INTELLECTUAL_PROPERTY,
    "confidentiality": ClauseType.CONFIDENTIALITY,
    "personal_data": ClauseType.PERSONAL_DATA,
}


@dataclass
class ContractSummary:
    subject: str | None = None
    price: str | None = None
    payment_terms: str | None = None
    term: str | None = None
    termination: str | None = None
    liability: str | None = None
    governing_law: str | None = None
    dispute_resolution: str | None = None
    ip: str | None = None
    confidentiality: str | None = None
    personal_data: str | None = None
    major_obligations: list[str] | None = None


def build_summary(clauses: list[ExtractedClause], obligation_excerpts: list[str]) -> ContractSummary:
    values: dict[str, str | None] = {}
    for field_name, clause_type in _SUMMARY_FIELDS.items():
        match = next((c for c in clauses if c.clause_type == clause_type), None)
        values[field_name] = match.normalized_text[:300] if match else None

    return ContractSummary(major_obligations=obligation_excerpts[:10], **values)
