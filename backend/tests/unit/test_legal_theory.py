"""Legal Theory Layer — the deterministic fact-pattern half only (no LLM
calls happen in this module; the legal-authority verification step is
tested separately in tests/integration/test_legal_theory_verification.py).
Synthetic fixtures throughout, deliberately different from any real case.
"""
from __future__ import annotations

from datetime import date

from app.domains.litigation.legal_theory import (
    ContractSignal,
    PaymentSignal,
    evaluate_contract_formation_by_conduct,
    evaluate_corporate_relationship_gaps,
)


def test_no_payments_no_contracts_has_no_preconditions_met():
    candidate = evaluate_contract_formation_by_conduct([], [])
    assert candidate.preconditions_met is False
    assert candidate.alternative_explanations  # always present, even on an empty case
    assert any("No payments" in f for f in candidate.contradicting_facts)


def test_single_payment_is_weaker_support_than_repeated():
    one = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1))], []
    )
    assert any("Only one payment" in f for f in one.contradicting_facts)

    many = evaluate_contract_formation_by_conduct(
        [
            PaymentSignal(payment_date=date(2025, 1, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1)),
            PaymentSignal(payment_date=date(2025, 2, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1)),
        ],
        [],
    )
    assert any("2 separate payments" in f for f in many.supporting_facts)


def test_consistent_referenced_agreement_date_is_supporting():
    candidate = evaluate_contract_formation_by_conduct(
        [
            PaymentSignal(payment_date=date(2025, 2, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1)),
            PaymentSignal(payment_date=date(2025, 3, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1)),
        ],
        [],
    )
    assert any("consistently cite the same date" in f for f in candidate.supporting_facts)


def test_no_referenced_agreement_at_all_is_contradicting():
    candidate = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="100000.00", referenced_contract_date=None)], []
    )
    assert any("no payment states a referenced agreement" in f.lower() for f in candidate.contradicting_facts)


def test_payment_predating_referenced_agreement_is_contradicting():
    candidate = evaluate_contract_formation_by_conduct(
        [
            PaymentSignal(payment_date=date(2024, 1, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1)),
            PaymentSignal(payment_date=date(2025, 2, 1), amount="100000.00", referenced_contract_date=date(2025, 1, 1)),
        ],
        [],
    )
    assert any("predate the earliest referenced agreement" in f for f in candidate.contradicting_facts)


def test_matching_contract_amount_is_supporting():
    candidate = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="500000.00", referenced_contract_date=date(2025, 1, 1))],
        [
            ContractSignal(
                document_title="draft.pdf", amounts=["500000.00"], maturity_dates=[], formation_clause_present=True,
                signature_status="unknown", notarized=False,
            )
        ],
    )
    assert any("exactly match" in f for f in candidate.supporting_facts)


def test_mismatched_contract_amount_is_contradicting_with_alternative():
    candidate = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="500000.00", referenced_contract_date=date(2025, 1, 1))],
        [
            ContractSignal(
                document_title="draft.pdf", amounts=["9000000.00"], maturity_dates=[], formation_clause_present=True,
                signature_status="unknown", notarized=False,
            )
        ],
    )
    assert any("None of the contract-stated amount" in f for f in candidate.contradicting_facts)
    assert candidate.alternative_explanations


def test_signed_contract_is_supporting_unsigned_produces_evidence_gap():
    unsigned = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="500000.00", referenced_contract_date=date(2025, 1, 1))],
        [
            ContractSignal(
                document_title="draft.pdf", amounts=[], maturity_dates=[], formation_clause_present=True,
                signature_status="unsigned_or_draft", notarized=False,
            )
        ],
    )
    assert any("no confirmed signature" in f for f in unsigned.contradicting_facts)
    assert unsigned.evidence_gaps
    assert unsigned.evidence_gaps[0].strengthens_theory_if_obtained == "critical"

    signed = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="500000.00", referenced_contract_date=date(2025, 1, 1))],
        [
            ContractSignal(
                document_title="signed.pdf", amounts=[], maturity_dates=[], formation_clause_present=True,
                signature_status="confirmed_signed", notarized=False,
            )
        ],
    )
    assert any("confirmed signed copy" in f for f in signed.supporting_facts)


def test_notarized_agreement_is_supporting():
    candidate = evaluate_contract_formation_by_conduct(
        [],
        [
            ContractSignal(
                document_title="notarized.pdf", amounts=[], maturity_dates=[], formation_clause_present=True,
                signature_status="unknown", notarized=True,
            )
        ],
    )
    assert any("notarized" in f for f in candidate.supporting_facts)


def test_later_payment_behavior_after_second_agreement_is_supporting():
    candidate = evaluate_contract_formation_by_conduct(
        [
            PaymentSignal(payment_date=date(2025, 1, 1), amount="100000.00", referenced_contract_date=date(2024, 12, 1)),
            PaymentSignal(payment_date=date(2025, 6, 1), amount="200000.00", referenced_contract_date=date(2025, 5, 1)),
            PaymentSignal(payment_date=date(2025, 7, 1), amount="200000.00", referenced_contract_date=date(2025, 5, 1)),
        ],
        [],
    )
    assert any("on or after the later referenced agreement date" in f for f in candidate.supporting_facts)


def test_alternative_explanations_always_present():
    candidate = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="500000.00", referenced_contract_date=date(2025, 1, 1))],
        [
            ContractSignal(
                document_title="signed.pdf", amounts=["500000.00"], maturity_dates=[], formation_clause_present=True,
                signature_status="confirmed_signed", notarized=True,
            )
        ],
    )
    # Even a strongly-supported fact pattern must still carry the standard
    # alternative reading — the module never becomes one-sided advocacy.
    assert len(candidate.alternative_explanations) >= 2


def test_research_question_never_contains_case_specific_content():
    candidate = evaluate_contract_formation_by_conduct(
        [PaymentSignal(payment_date=date(2025, 1, 1), amount="500000.00", referenced_contract_date=date(2025, 1, 1))], []
    )
    # A generic legal question — never a company name, amount, or date.
    assert "500000" not in candidate.research_question
    assert "2025" not in candidate.research_question
    assert "заём" in candidate.research_question.lower() or "loan" in candidate.research_question.lower()


# --- Corporate relationship evidence gaps ---


def test_corporate_relationship_gap_produced_when_only_one_side_documented():
    gaps = evaluate_corporate_relationship_gaps(
        relationship_found=True, other_party_registry_document_present=False,
        documented_party_name="ООО Ромашка", other_party_name="ООО Клиент",
    )
    assert len(gaps) == 1
    assert "ООО Клиент" in gaps[0].missing_fact
    assert gaps[0].strengthens_theory_if_obtained == "significant"


def test_no_gap_when_both_sides_documented():
    gaps = evaluate_corporate_relationship_gaps(
        relationship_found=True, other_party_registry_document_present=True,
        documented_party_name="ООО Ромашка", other_party_name="ООО Клиент",
    )
    assert gaps == []


def test_no_gap_when_no_relationship_found_at_all():
    gaps = evaluate_corporate_relationship_gaps(
        relationship_found=False, other_party_registry_document_present=False,
        documented_party_name="ООО Ромашка", other_party_name="ООО Клиент",
    )
    assert gaps == []
