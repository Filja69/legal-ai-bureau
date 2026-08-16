from __future__ import annotations

from app.domains.contracts.alternative_clause import propose_alternative
from app.domains.contracts.recommendations import recommend
from app.domains.contracts.redline import word_diff
from app.domains.contracts.risk_detection import RiskCandidate
from app.domains.contracts.risk_verification import VerifiedRisk
from app.domains.contracts.severity import SeverityInputs
from app.models.contracts import RecommendationAction, RiskCategory, RiskClassification, RiskType, RiskVerificationStatus


def _verified(
    detector="liability", classification=RiskClassification.HIGH_RISK, clause_index=0,
    severity_inputs=None, verification_status=RiskVerificationStatus.MOCK,
):
    candidate = RiskCandidate(
        detector=detector, risk_type=RiskType.UNLIMITED_LIABILITY, category=RiskCategory.FINANCIAL,
        classification=classification, title="t", description="d", why_it_matters="w",
        severity_inputs=severity_inputs or SeverityInputs(legal_impact=60, financial_impact=80, probability=40, scope=60,
            irreversibility=50),
        clause_index=clause_index,
    )
    return VerifiedRisk(
        candidate=candidate, verification_status=verification_status, legal_basis="basis",
        citations=["ст. 1"], confidence="medium", research_id="r1", has_conflicting_practice=False,
    )


# --- recommendations ---


def test_recommend_add_for_missing_protection():
    risk = _verified(classification=RiskClassification.MISSING_PROTECTION, clause_index=None)
    rec = recommend(risk)
    assert rec.action == RecommendationAction.ADD


def test_recommend_rewrite_for_high_severity_specific_clause():
    risk = _verified(severity_inputs=SeverityInputs(legal_impact=80, financial_impact=80, probability=60, scope=60, irreversibility=60))
    rec = recommend(risk)
    assert rec.action == RecommendationAction.REWRITE
    assert rec.priority <= 2


def test_recommend_keep_for_low_severity():
    risk = _verified(severity_inputs=SeverityInputs(legal_impact=5, financial_impact=5, probability=5, scope=5, irreversibility=5))
    rec = recommend(risk)
    assert rec.action == RecommendationAction.KEEP


def test_recommend_negotiate_for_structural_finding_without_clause():
    risk = _verified(classification=RiskClassification.UNFAVORABLE, clause_index=None,
                      severity_inputs=SeverityInputs(legal_impact=30, financial_impact=30, probability=30, scope=30, irreversibility=30))
    rec = recommend(risk)
    assert rec.action == RecommendationAction.NEGOTIATE


def test_recommendation_carries_legal_and_commercial_reason():
    risk = _verified()
    rec = recommend(risk)
    assert rec.legal_basis == "basis"
    assert rec.commercial_reason == "w"


# --- alternative clause ---


def test_propose_alternative_for_known_detector():
    risk = _verified(detector="liability")
    draft = propose_alternative(risk)
    assert draft is not None
    assert "ограничена" in draft.proposed_text
    assert draft.change_reason


def test_propose_alternative_returns_none_for_unknown_detector():
    risk = _verified(detector="unmapped_detector")
    assert propose_alternative(risk) is None


def test_propose_alternative_returns_none_without_clause_index():
    risk = _verified(detector="liability", clause_index=None)
    assert propose_alternative(risk) is None


# --- redline ---


def test_word_diff_detects_insertion():
    ops = word_diff("Заказчик вправе отказаться от договора.", "Заказчик вправе отказаться от договора, уведомив за 10 дней.")
    assert any(o.op == "insert" for o in ops)
    assert any(o.op == "equal" for o in ops)


def test_word_diff_detects_deletion():
    ops = word_diff("без уведомления и без объяснения причин", "уведомив Исполнителя за 10 рабочих дней")
    assert any(o.op == "delete" for o in ops)
    assert any(o.op == "insert" for o in ops)


def test_word_diff_identical_text_is_all_equal():
    text = "Стороны несут ответственность в соответствии с законодательством РФ."
    ops = word_diff(text, text)
    assert all(o.op == "equal" for o in ops)


def test_word_diff_reconstructs_proposed_text_from_equal_and_insert():
    original = "Ответственность не ограничена."
    proposed = "Ответственность ограничена суммой договора."
    ops = word_diff(original, proposed)
    reconstructed = "".join(o.text for o in ops if o.op in ("equal", "insert"))
    assert reconstructed == proposed
