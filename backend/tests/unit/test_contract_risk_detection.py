from __future__ import annotations

from app.domains.contracts.risk_detection import (
    AmbiguityDetector,
    ChangeControlDetector,
    ConfidentialityDetector,
    DisputeRiskDetector,
    LiabilityDetector,
    MissingClauseDetector,
    PaymentRiskDetector,
    PenaltyDetector,
    PersonalDataDetector,
    TerminationDetector,
    run_all_detectors,
)
from app.domains.contracts.severity import SeverityInputs, compute_score, score_to_severity
from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.models.contracts import ContractRiskSeverity, ContractType, RiskClassification

_RISKY_CONTRACT = """1. Предмет договора

1.1. Исполнитель обязуется оказать услуги, а Заказчик обязуется принять и оплатить услуги.

2. Порядок оплаты

2.1. Заказчик осуществляет 100% предоплату до начала оказания услуг.

3. Ответственность сторон

3.1. Ответственность Исполнителя перед Заказчиком не ограничивается и наступает в полном объеме, включая косвенные убытки.

4. Расторжение

4.1. Заказчик вправе отказаться от исполнения договора в любое время без уведомления и без объяснения причин.

5. Неустойка

5.1. В случае просрочки Заказчик уплачивает Исполнителю неустойку в размере 0.5% от суммы договора за каждый день просрочки.

6. Конфиденциальность

6.1. Исполнитель обязуется сохранять конфиденциальность информации, полученной от Заказчика,
при необходимости согласовывая раскрытие в разумный срок.
"""

_CLEAN_CONTRACT = """1. Предмет договора

1.1. Исполнитель обязуется оказать услуги, а Заказчик обязуется принять и оплатить услуги.

2. Порядок оплаты

2.1. Заказчик оплачивает услуги в течение 10 рабочих дней после подписания акта.

3. Ответственность сторон

3.1. Ответственность каждой из сторон ограничена суммой договора и не более фактически понесенного реального ущерба.

4. Расторжение

4.1. Любая из сторон вправе отказаться от договора, уведомив другую сторону за 30 календарных дней.

5. Разрешение споров

5.1. Споры разрешаются в Арбитражном суде города Москвы.

6. Применимое право

6.1. Договор регулируется законодательством Российской Федерации.
"""


def _extract(text: str):
    return ContractStructureExtractor().extract(text)


def test_liability_detector_flags_uncapped_liability():
    clauses = _extract(_RISKY_CONTRACT)
    candidates = LiabilityDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) == 1
    assert candidates[0].classification == RiskClassification.HIGH_RISK
    assert candidates[0].research_question is not None


def test_liability_detector_does_not_flag_capped_liability():
    clauses = _extract(_CLEAN_CONTRACT)
    candidates = LiabilityDetector().detect(clauses, ContractType.SERVICE)
    assert candidates == []


def test_termination_detector_flags_no_notice_termination():
    clauses = _extract(_RISKY_CONTRACT)
    candidates = TerminationDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) == 1
    assert "уведомления" in candidates[0].description


def test_termination_detector_does_not_flag_notice_period():
    clauses = _extract(_CLEAN_CONTRACT)
    candidates = TerminationDetector().detect(clauses, ContractType.SERVICE)
    assert candidates == []


def test_payment_risk_detector_flags_full_prepayment():
    clauses = _extract(_RISKY_CONTRACT)
    candidates = PaymentRiskDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) == 1


def test_ambiguity_detector_flags_vague_language():
    clauses = _extract(_RISKY_CONTRACT)
    candidates = AmbiguityDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) >= 1


def test_penalty_detector_flags_one_sided_penalty():
    clauses = _extract(_RISKY_CONTRACT)
    candidates = PenaltyDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) == 1


def test_missing_clause_detector_flags_missing_confidentiality_for_nda():
    clauses = _extract("1. Предмет договора\n\n1.1. Стороны обмениваются информацией.\n")
    candidates = MissingClauseDetector().detect(clauses, ContractType.NDA)
    missing_titles = [c.title for c in candidates]
    assert any("confidentiality" in t for t in missing_titles)


def test_confidentiality_detector_flags_missing_clause_for_nda():
    clauses = _extract("1. Предмет договора\n\n1.1. Стороны обмениваются информацией.\n")
    candidates = ConfidentialityDetector().detect(clauses, ContractType.NDA)
    assert len(candidates) == 1
    assert candidates[0].clause_index is None


def test_dispute_risk_detector_flags_missing_dispute_clause():
    clauses = _extract(_RISKY_CONTRACT)
    candidates = DisputeRiskDetector().detect(clauses, ContractType.SERVICE)
    assert any(c.risk_type.value == "dispute_risk" for c in candidates)


def test_dispute_risk_detector_no_flag_when_clause_present():
    clauses = _extract(_CLEAN_CONTRACT)
    candidates = DisputeRiskDetector().detect(clauses, ContractType.SERVICE)
    assert candidates == []


def test_personal_data_detector_flags_unaddressed_mention():
    clauses = _extract("1. Обработка данных\n\n1.1. Стороны обрабатывают персональные данные субъектов.\n")
    candidates = PersonalDataDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) == 1


def test_personal_data_detector_silent_when_not_mentioned():
    clauses = _extract(_CLEAN_CONTRACT)
    candidates = PersonalDataDetector().detect(clauses, ContractType.SERVICE)
    assert candidates == []


def test_change_control_detector_flags_missing_clause_for_service_contract():
    clauses = _extract(_CLEAN_CONTRACT)
    candidates = ChangeControlDetector().detect(clauses, ContractType.SERVICE)
    assert len(candidates) == 1


def test_change_control_detector_silent_for_nda():
    clauses = _extract(_CLEAN_CONTRACT)
    candidates = ChangeControlDetector().detect(clauses, ContractType.NDA)
    assert candidates == []


def test_run_all_detectors_finds_more_risks_in_risky_contract_than_clean():
    risky = run_all_detectors(_extract(_RISKY_CONTRACT), ContractType.SERVICE)
    clean = run_all_detectors(_extract(_CLEAN_CONTRACT), ContractType.SERVICE)
    assert len(risky) > len(clean)


def test_run_all_detectors_every_candidate_has_a_valid_severity_score():
    candidates = run_all_detectors(_extract(_RISKY_CONTRACT), ContractType.SERVICE)
    for c in candidates:
        score = compute_score(c.severity_inputs)
        assert 0 <= score <= 100


# --- severity scoring ---


def test_severity_inputs_reject_out_of_range_values():
    import pytest

    with pytest.raises(ValueError):
        SeverityInputs(legal_impact=150, financial_impact=0, probability=0, scope=0, irreversibility=0)


def test_score_to_severity_boundaries():
    assert score_to_severity(0) == ContractRiskSeverity.INFO
    assert score_to_severity(9) == ContractRiskSeverity.INFO
    assert score_to_severity(10) == ContractRiskSeverity.LOW
    assert score_to_severity(30) == ContractRiskSeverity.LOW
    assert score_to_severity(31) == ContractRiskSeverity.MEDIUM
    assert score_to_severity(50) == ContractRiskSeverity.MEDIUM
    assert score_to_severity(51) == ContractRiskSeverity.HIGH
    assert score_to_severity(75) == ContractRiskSeverity.HIGH
    assert score_to_severity(76) == ContractRiskSeverity.CRITICAL
    assert score_to_severity(100) == ContractRiskSeverity.CRITICAL


def test_compute_score_is_deterministic():
    inputs = SeverityInputs(legal_impact=40, financial_impact=80, probability=35, scope=60, irreversibility=50)
    assert compute_score(inputs) == compute_score(inputs)
    assert compute_score(inputs) == round(40 * 0.3 + 80 * 0.3 + 35 * 0.2 + 60 * 0.1 + 50 * 0.1)
