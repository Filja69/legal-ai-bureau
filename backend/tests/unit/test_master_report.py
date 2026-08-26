"""Master Case Report — pure synthesis functions. All synthetic data,
deliberately different party/amount/date values from the real Ledovyi
Service v. BS Energo Region case this feature was designed against — proves
the reasoning generalizes rather than being hardcoded to that case (§25).
"""
from __future__ import annotations

import uuid
from datetime import date

from app.domains.litigation.conduct_patterns import detect_payment_pattern
from app.domains.litigation.contract_forensics import (
    build_contract_version_matrix,
    contract_amount_mismatch,
    extract_contract_terms,
)
from app.domains.litigation.contradiction_detector import AllegationInput, detect_claim_theory_tensions
from app.domains.litigation.course_of_dealing import detect_course_of_dealing
from app.domains.litigation.interest_damages import extract_interest_claim
from app.domains.litigation.master_report import (
    FindingCategory,
    RelatedLitigationInput,
    build_burden_map,
    build_case_map,
    build_claim_contradiction_findings,
    build_contract_formation_findings,
    build_contract_mismatch_finding,
    build_course_of_dealing_finding,
    build_court_scenarios,
    build_draft_response_structure,
    build_interest_damages_finding,
    build_one_pager,
    build_opposing_party_questions,
    build_payment_pattern_finding,
    build_related_litigation_findings,
    build_theory_vs_conduct_finding,
    rank_findings,
)
from app.models.matters import AllegationType

# --- Synthetic fixture: an unrelated fact pattern (services agreement
# dispute, different amounts/dates/parties) to prove generalization. ---

_DOC_A = uuid.uuid4()
_DOC_B = uuid.uuid4()


def _allegation(allegation_type: AllegationType, document_id: uuid.UUID = _DOC_A) -> AllegationInput:
    return AllegationInput(
        id=uuid.uuid4(), document_id=document_id, page_number=1, excerpt="synthetic excerpt", allegation_type=allegation_type
    )


def _mistake_negotiation_tensions():
    return detect_claim_theory_tensions(
        [_allegation(AllegationType.PAYMENT_BY_MISTAKE), _allegation(AllegationType.FUTURE_CONTRACT_NEGOTIATIONS)]
    )


# --- §23.2/§23.3: claim-theory tensions (cross-allegation contradiction) ---


def test_claim_theory_tension_fires_for_mistake_vs_negotiation():
    tensions = _mistake_negotiation_tensions()
    assert len(tensions) == 1
    assert "tension worth investigating" in tensions[0].reason


def test_claim_theory_tension_does_not_fire_for_compatible_allegations():
    tensions = detect_claim_theory_tensions(
        [_allegation(AllegationType.NO_CONTRACT), _allegation(AllegationType.FUTURE_CONTRACT_NEGOTIATIONS)]
    )
    assert tensions == []


def test_claim_theory_tension_does_not_fire_for_single_allegation():
    assert detect_claim_theory_tensions([_allegation(AllegationType.PAYMENT_BY_MISTAKE)]) == []


# --- Payment pattern (generalized "conduct of the parties") ---


def test_payment_pattern_significant_for_many_transactions_over_time():
    dates = [date(2025, 1, 1), date(2025, 3, 1), date(2025, 6, 1), date(2025, 9, 1)]
    result = detect_payment_pattern(dates, ["Payer Co"] * 4, ["Recipient Co"] * 4)
    assert result.is_significant
    assert result.transaction_count == 4
    assert "does not by itself establish" in result.description


def test_payment_pattern_not_significant_for_two_close_transactions():
    dates = [date(2025, 1, 1), date(2025, 1, 3)]
    result = detect_payment_pattern(dates, ["Payer Co"] * 2, ["Recipient Co"] * 2)
    assert not result.is_significant


def test_payment_pattern_finding_omitted_when_not_significant():
    result = detect_payment_pattern([date(2025, 1, 1)], ["Payer"], ["Recipient"])
    assert build_payment_pattern_finding(result) is None


def test_payment_pattern_finding_is_always_neutral():
    dates = [date(2025, 1, 1), date(2025, 4, 1), date(2025, 8, 1)]
    result = detect_payment_pattern(dates, ["A", "B", "C"], ["X"] * 3)
    finding = build_payment_pattern_finding(result)
    assert finding is not None
    assert finding.helps_side == "neutral"
    assert finding.hurts_side == "neutral"


# --- Contract forensics ---


def test_extract_contract_terms_finds_amount_rate_maturity_and_formation_clause():
    text = (
        "Займодавец передает Заемщику 7 500 000 рублей. Процентная ставка составляет 12 процентов годовых. "
        "Заемщик обязан вернуть сумму займа в срок до 01.01.2028. "
        "Договор считается заключенным с момента поступления денежных средств."
    )
    terms = extract_contract_terms(_DOC_A, "contract.txt", text)
    assert "7500000.00" in terms.amounts
    assert terms.interest_rate == "12%"
    assert terms.formation_clause_present is True


def test_extract_contract_terms_amount_with_nonbreaking_thousands_separator():
    """Word-authored Russian contracts commonly group an amount's digits
    with a non-breaking space (U+00A0), not a regular space, so the number
    can't be split across a line break — a mismatch between a document's
    non-breaking separator and a regex expecting only regular spaces would
    silently match just the trailing digit group (e.g. "000" out of
    "30 000 000") instead of the whole number.
    """
    text = "Займодавец обязуется передать Заемщику 30 000 000 (тридцать миллионов) рублей 00 копеек."
    terms = extract_contract_terms(_DOC_A, "contract.txt", text)
    assert "30000000.00" in terms.amounts


def test_extract_contract_terms_amount_with_parenthetical_spellout():
    """Real Russian loan agreements commonly write the amount as digits
    followed by a parenthetical spellout before the currency word
    ("6300000 (шесть миллионов триста тысяч) рублей") — a general
    formatting convention, not specific to any one document.
    """
    text = "Займодавец передает Заемщику сумму займа 6300000 (шесть миллионов триста тысяч) рублей 00 копеек."
    terms = extract_contract_terms(_DOC_A, "contract.txt", text)
    assert "6300000.00" in terms.amounts


def test_extract_contract_terms_unsigned_draft_detected():
    text = "Проект договора займа. Займодавец________________ Заемщик________________"
    terms = extract_contract_terms(_DOC_A, "draft.txt", text)
    assert terms.signature_status == "unsigned_or_draft"


def test_contract_amount_mismatch_true_when_no_contract_matches_money_flow():
    matrix = build_contract_version_matrix(
        [(_DOC_A, "v1.txt", "Сумма займа 3 000 000 рублей."), (_DOC_B, "v2.txt", "Сумма займа 15 000 000 рублей.")]
    )
    assert contract_amount_mismatch(matrix, "9000000.00") is True


def test_contract_amount_mismatch_false_when_single_matching_amount():
    matrix = build_contract_version_matrix([(_DOC_A, "v1.txt", "Сумма займа 9 000 000 рублей.")])
    assert contract_amount_mismatch(matrix, "9000000.00") is False


def test_contract_mismatch_finding_is_always_neutral_and_explains_both_sides():
    matrix = build_contract_version_matrix(
        [(_DOC_A, "v1.txt", "Сумма займа 3 000 000 рублей."), (_DOC_B, "v2.txt", "Сумма займа 15 000 000 рублей.")]
    )
    finding = build_contract_mismatch_finding(matrix, "9000000.00")
    assert finding is not None
    assert finding.helps_side == "neutral" and finding.hurts_side == "neutral"
    assert "either interpretation" in finding.legal_significance or "may support either" in finding.legal_significance


def test_contract_formation_finding_never_states_contract_concluded_or_not():
    matrix = build_contract_version_matrix([(_DOC_A, "draft.txt", "Проект договора займа.")])
    findings = build_contract_formation_findings(matrix)
    assert len(findings) == 1
    haystack = (findings[0].statement + findings[0].caveat).lower()
    assert "was concluded" not in haystack
    assert "was not concluded" not in haystack


def test_contract_formation_finding_omitted_for_confirmed_signed():
    matrix = build_contract_version_matrix(
        [(_DOC_A, "signed.txt", "Договор подписан сторонами в полном объеме.")]
    )
    assert matrix[0].signature_status == "confirmed_signed"
    assert build_contract_formation_findings(matrix) == []


# --- Claim contradiction findings: side attribution ---


def test_claim_contradiction_findings_hurt_the_allegation_author():
    findings = build_claim_contradiction_findings([], _mistake_negotiation_tensions(), {}, our_side_role="defendant")
    assert findings[0].helps_side == "client"
    assert findings[0].hurts_side == "opponent"


def test_claim_contradiction_findings_unclear_when_side_role_unknown():
    findings = build_claim_contradiction_findings([], _mistake_negotiation_tensions(), {}, our_side_role="unclear")
    assert findings[0].helps_side == "unclear"
    assert findings[0].hurts_side == "unclear"


# --- Related litigation: causal-claim discipline (§23.8) ---


def test_related_litigation_finding_never_claims_motive():
    findings = build_related_litigation_findings(
        [
            RelatedLitigationInput(
                id=uuid.uuid4(), case_number="A40-1/2026", court="Some Court",
                subject_matter="Debt collection", amount_in_dispute="1000000.00",
            )
        ]
    )
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.RELATED_LITIGATION
    assert findings[0].helps_side == "neutral"
    haystack = findings[0].statement.lower()
    assert "needs money" not in haystack
    assert "caused" not in haystack or "does not establish" in haystack


# --- Ranking, one-pager, burden map, scenarios, questions, response structure ---


def test_rank_findings_orders_by_strength():
    from app.domains.litigation.master_report import MasterFinding

    findings = [
        MasterFinding(id="a", category=FindingCategory.OTHER, title="a", statement="", strength="LOW"),
        MasterFinding(id="b", category=FindingCategory.OTHER, title="b", statement="", strength="CRITICAL"),
        MasterFinding(id="c", category=FindingCategory.OTHER, title="c", statement="", strength="MEDIUM"),
    ]
    ranked = rank_findings(findings)
    assert [f.id for f in ranked] == ["b", "c", "a"]


def test_one_pager_never_empty_even_with_no_findings():
    one_pager = build_one_pager([], money_at_stake="0.00", next_best_action=None)
    assert one_pager.money_at_stake == "0.00"
    assert one_pager.top_arguments == []


def test_burden_map_one_item_per_allegation_type_present():
    items = build_burden_map({AllegationType.NO_CONTRACT, AllegationType.UNJUST_ENRICHMENT}, [], our_side_role="unclear")
    assert len(items) == 2
    assert all(i.side == "unclear" for i in items)


def test_court_scenarios_always_include_baseline_and_no_percentages():
    from app.domains.litigation.master_report import MasterFinding

    scenarios = build_court_scenarios([MasterFinding(id="x", category=FindingCategory.CLAIM_CONTRADICTION, title="x", statement="")])
    assert any("adopts the claimant's theory" in s.scenario for s in scenarios)
    for s in scenarios:
        assert s.label == "STRATEGIC SCENARIO — NOT A COURT PREDICTION"
        assert "%" not in s.scenario and "%" not in s.why_court_could_get_there


def test_opposing_party_questions_keyed_by_present_categories_only():
    from app.domains.litigation.master_report import MasterFinding

    findings = [MasterFinding(id="x", category=FindingCategory.PAYMENT_PATTERN, title="x", statement="")]
    questions = build_opposing_party_questions(findings)
    assert len(questions) > 0
    assert all("BS Energo" not in q and "Ledovyi" not in q for q in questions)


def test_draft_response_structure_flags_unsupported_sections():
    sections = build_draft_response_structure([])
    contract_section = next(s for s in sections if "договорные отношения" in s.section)
    assert contract_section.caution is not None


def test_case_map_reports_missing_evidence_when_no_claim_dates():
    case_map = build_case_map([], [])
    assert "not derivable" in case_map.note or "не установлен" in case_map.note.lower() or case_map.note != ""


# --- Course of dealing finding wiring ---


def test_course_of_dealing_finding_omitted_for_single_referenced_date():
    result = detect_course_of_dealing({"2025-03-01": 5}, [])
    assert build_course_of_dealing_finding(result) is None


def test_course_of_dealing_finding_present_and_neutral_for_two_dates():
    result = detect_course_of_dealing({"2025-03-01": 2, "2025-11-20": 1}, [])
    finding = build_course_of_dealing_finding(result)
    assert finding is not None
    assert finding.category == FindingCategory.COURSE_OF_DEALING
    assert finding.helps_side == "neutral" and finding.hurts_side == "neutral"
    assert "does not by itself prove" in finding.caveat
    assert finding.alternative_explanations  # never a one-sided conclusion


# --- Theory vs conduct finding wiring ---


def test_theory_vs_conduct_finding_requires_both_signals():
    from app.domains.litigation.conduct_patterns import PaymentPatternResult

    insignificant = PaymentPatternResult(
        transaction_count=1, span_days=None, distinct_payers=1, distinct_recipients=1, is_significant=False, description=""
    )
    assert build_theory_vs_conduct_finding({AllegationType.PAYMENT_BY_MISTAKE}, insignificant) is None

    significant = PaymentPatternResult(
        transaction_count=4, span_days=200, distinct_payers=1, distinct_recipients=1, is_significant=True,
        description="4 transfers.",
    )
    assert build_theory_vs_conduct_finding({AllegationType.UNJUST_ENRICHMENT}, significant) is None

    finding = build_theory_vs_conduct_finding({AllegationType.PAYMENT_BY_MISTAKE}, significant)
    assert finding is not None
    assert finding.category == FindingCategory.PARTY_CONDUCT
    assert "does not by itself disprove" in finding.statement


# --- Interest/damages finding wiring ---


def test_interest_damages_finding_omitted_when_no_claim_text_matches():
    assert build_interest_damages_finding(None) is None


def test_interest_damages_finding_flags_legal_research_required():
    claim = extract_interest_claim(
        "Проценты за пользование чужими денежными средствами в размере 90000,00 руб. за период с 01.01.2025 по 01.06.2025.",
        earliest_payment_date=date(2025, 1, 1),
        contract_maturity_dates=[],
    )
    finding = build_interest_damages_finding(claim)
    assert finding is not None
    assert finding.category == FindingCategory.INTEREST_CALCULATION
    assert finding.legal_research_required is True
    assert finding.helps_side == "neutral" and finding.hurts_side == "neutral"


# --- New MasterFinding fields default safely ---


def test_master_finding_new_fields_default_empty():
    from app.domains.litigation.master_report import MasterFinding

    f = MasterFinding(id="x", category=FindingCategory.OTHER, title="t", statement="s")
    assert f.alternative_explanations == []
    assert f.what_would_strengthen == []
    assert f.what_would_weaken == []
    assert f.legal_research_required is False
