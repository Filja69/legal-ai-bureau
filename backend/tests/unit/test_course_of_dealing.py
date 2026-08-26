"""Course-of-dealing detection — synthetic fixtures only, deliberately
different amounts/dates/rates from any real case. Anti-overfitting focus:
a single referenced contract date must never be treated as a pattern, and
the finding must never claim a later contract "proves" an earlier one.
"""
from __future__ import annotations

import uuid

from app.domains.litigation.contract_forensics import ContractVersionTerms
from app.domains.litigation.course_of_dealing import detect_course_of_dealing

_DOC_A = uuid.uuid4()
_DOC_B = uuid.uuid4()


def _terms(document_id: uuid.UUID, *, rate: str | None, formation_clause: bool) -> ContractVersionTerms:
    return ContractVersionTerms(
        document_id=document_id, document_title="doc.txt", amounts=[], interest_rate=rate,
        maturity_dates=[], formation_clause_present=formation_clause,
    )


def test_single_referenced_date_is_not_a_pattern():
    """A synthetic case with 4 payments all referencing the SAME contract
    date must never be flagged as course-of-dealing — this is the ordinary
    case, not a pattern.
    """
    result = detect_course_of_dealing({"2025-01-01": 4}, [])
    assert result.is_significant is False
    assert "single contractual basis" in result.description


def test_two_distinct_dates_is_significant_and_never_claims_proof():
    result = detect_course_of_dealing({"2025-01-01": 3, "2025-06-15": 1}, [])
    assert result.is_significant is True
    assert len(result.distinct_contract_dates) == 2
    assert "does not by itself prove" in result.description


def test_matching_contract_terms_are_counted_but_not_over_claimed():
    matrix = [
        _terms(_DOC_A, rate="8%", formation_clause=True),
        _terms(_DOC_B, rate="8%", formation_clause=True),
    ]
    result = detect_course_of_dealing({"2025-01-01": 2, "2025-09-01": 1}, matrix)
    assert result.matching_term_document_pairs == 1
    assert "matching interest rate" in result.description


def test_differing_contract_terms_do_not_falsely_claim_a_match():
    matrix = [
        _terms(_DOC_A, rate="8%", formation_clause=True),
        _terms(_DOC_B, rate="15%", formation_clause=False),
    ]
    result = detect_course_of_dealing({"2025-01-01": 2, "2025-09-01": 1}, matrix)
    assert result.matching_term_document_pairs == 0
    assert "matching interest rate" not in result.description


def test_no_referenced_dates_at_all_is_not_significant():
    result = detect_course_of_dealing({}, [])
    assert result.is_significant is False
