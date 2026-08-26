"""Course-of-dealing detection (reasoning pattern: earlier draft/contract +
later formal/renewed contract + similar terms + a later payment referencing
the later contract -> possible ongoing lending relationship, not proof of
either document alone). Fully generalized: works off `MoneyFlowSummary.
referenced_contract_dates` (already computed by payment_extractor.py, keyed
purely on what payment purposes actually state) and `ContractVersionTerms`
(already computed by contract_forensics.py) — no case-specific text, no new
extraction of a contract's own "as of" date (which would require a much
less reliable heuristic than the payment-purpose references already proven
reliable elsewhere in this package).

Never concludes that a later contractual reference proves an earlier
arrangement's terms or existence, or vice versa — every finding this module
feeds carries that caveat explicitly (see master_report.py's
`build_course_of_dealing_finding`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domains.litigation.contract_forensics import ContractVersionTerms

# A single distinct referenced contract date is the ordinary case (all
# payments cite the same agreement) — not a pattern. Two or more distinct
# dates, each backed by at least one real payment, is a structural fact
# about the record itself, not a fuzzy heuristic, so no count/span threshold
# is needed the way conduct_patterns.py needs one for payment repetition.
_MIN_DISTINCT_DATES_FOR_PATTERN = 2


@dataclass
class CourseOfDealingResult:
    distinct_contract_dates: list[date]
    payments_per_date: dict[str, int]
    matching_term_document_pairs: int
    is_significant: bool
    description: str


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _has_matching_terms(a: ContractVersionTerms, b: ContractVersionTerms) -> bool:
    """Two contract documents "match" only on terms that are independently
    meaningful and non-trivial to share by coincidence — a shared interest
    rate is common; requiring the formation clause too (i.e. both documents
    use materially similar drafting, not just a common market rate) keeps
    this conservative.
    """
    return (
        a.interest_rate is not None
        and a.interest_rate == b.interest_rate
        and a.formation_clause_present
        and b.formation_clause_present
    )


def detect_course_of_dealing(
    referenced_contract_dates: dict[str, int],
    contract_matrix: list[ContractVersionTerms],
) -> CourseOfDealingResult:
    parsed_dates = sorted({parsed for raw in referenced_contract_dates if (parsed := _parse_iso_date(raw)) is not None})

    matching_pairs = 0
    for i in range(len(contract_matrix)):
        for j in range(i + 1, len(contract_matrix)):
            if _has_matching_terms(contract_matrix[i], contract_matrix[j]):
                matching_pairs += 1

    is_significant = len(parsed_dates) >= _MIN_DISTINCT_DATES_FOR_PATTERN

    if not is_significant:
        description = "Payments in this case reference a single contractual basis; no course-of-dealing pattern detected."
    else:
        terms_clause = (
            f" {matching_pairs} contract document pair(s) in the record share a matching interest rate and "
            "formation clause, which may be additional context for this pattern."
            if matching_pairs > 0
            else ""
        )
        description = (
            f"Payments in this case reference {len(parsed_dates)} distinct contractual dates "
            f"({', '.join(d.isoformat() for d in parsed_dates)}).{terms_clause} A later contractual reference "
            "does not by itself prove the terms or existence of an earlier arrangement, and an earlier "
            "reference does not by itself extend to cover a later, separately-referenced transfer — each "
            "transfer's legal basis must be assessed on its own record."
        )

    return CourseOfDealingResult(
        distinct_contract_dates=parsed_dates,
        payments_per_date=dict(referenced_contract_dates),
        matching_term_document_pairs=matching_pairs,
        is_significant=is_significant,
        description=description,
    )
