"""E2 — CLAIM_VS_EVIDENCE contradiction rule. Pure-function unit tests
against synthetic AllegationInput/PaymentOrderInput — no DB.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.domains.litigation.contradiction_detector import (
    AllegationInput,
    PaymentOrderInput,
    detect_claim_vs_evidence_contradictions,
)
from app.models.matters import AllegationType, ContradictionType


def _allegation(allegation_type: AllegationType) -> AllegationInput:
    return AllegationInput(
        id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=1,
        excerpt="Договор впоследствии не был заключен сторонами.", allegation_type=allegation_type,
    )


def _loan_payment(contract_date: date = date(2024, 9, 11)) -> PaymentOrderInput:
    return PaymentOrderInput(
        id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=1,
        excerpt="Перечисление средств по договору процентного займа б/н от 11.09.2024г.",
        referenced_contract_type="договор процентного займа", referenced_contract_date=contract_date,
    )


def _non_loan_payment() -> PaymentOrderInput:
    return PaymentOrderInput(
        id=uuid.uuid4(), document_id=uuid.uuid4(), page_number=1,
        excerpt="Оплата по договору поставки №12.", referenced_contract_type=None, referenced_contract_date=None,
    )


def test_no_contract_allegation_plus_loan_payment_surfaces_potential_contradiction():
    contradictions = detect_claim_vs_evidence_contradictions([_allegation(AllegationType.NO_CONTRACT)], [_loan_payment()])
    assert len(contradictions) == 1
    result = contradictions[0]
    assert result.contradiction_type == ContradictionType.CLAIM_VS_EVIDENCE
    assert result.referenced_contract_date == date(2024, 9, 11)
    assert result.allegation_excerpt
    assert result.evidence_excerpt


def test_result_never_concludes_contract_was_concluded():
    """The safety-critical assertion: the caveat must always be present, and
    the reason text must never affirmatively conclude formation as an
    established fact (as opposed to merely describing what the allegation
    itself says, e.g. "alleges no contract was concluded" — that's the
    plaintiff's claim being quoted, not this system asserting a verdict).
    """
    result = detect_claim_vs_evidence_contradictions([_allegation(AllegationType.NO_CONTRACT)], [_loan_payment()])[0]
    assert "does not by itself establish that the contract was legally concluded" in result.caveat
    reason_lower = result.reason.lower()
    for forbidden_phrase in ("therefore the contract", "this proves", "this establishes", "confirms that the contract was concluded"):
        assert forbidden_phrase not in reason_lower


def test_multiple_loan_payments_each_produce_their_own_contradiction():
    payments = [_loan_payment(), _loan_payment(), _loan_payment()]
    contradictions = detect_claim_vs_evidence_contradictions([_allegation(AllegationType.NO_CONTRACT)], payments)
    assert len(contradictions) == 3


def test_other_allegation_types_do_not_trigger_this_rule():
    """Only NO_CONTRACT allegations are cross-checked against payment
    evidence this way — e.g. NO_LEGAL_BASIS alone (without a NO_CONTRACT
    allegation) must not surface a claim-vs-evidence contradiction.
    """
    contradictions = detect_claim_vs_evidence_contradictions([_allegation(AllegationType.NO_LEGAL_BASIS)], [_loan_payment()])
    assert contradictions == []


def test_false_positive_regression_non_loan_payment_never_contradicts_no_contract_allegation():
    """A generic 'оплата по договору [поставки]' payment must NOT be
    treated as contradicting a NO_CONTRACT (loan) allegation — this is the
    explicit false-positive regression the brief calls for.
    """
    contradictions = detect_claim_vs_evidence_contradictions([_allegation(AllegationType.NO_CONTRACT)], [_non_loan_payment()])
    assert contradictions == []


def test_no_allegations_at_all_yields_no_contradictions():
    contradictions = detect_claim_vs_evidence_contradictions([], [_loan_payment()])
    assert contradictions == []


def test_no_payment_orders_at_all_yields_no_contradictions():
    contradictions = detect_claim_vs_evidence_contradictions([_allegation(AllegationType.NO_CONTRACT)], [])
    assert contradictions == []
