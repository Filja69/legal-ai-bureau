"""ContractRecommendation engine — brief §35-36. Deterministic mapping from a
verified risk to one of KEEP/NEGOTIATE/REWRITE/REMOVE/ADD — not an LLM
judgment call, so the same risk always yields the same recommended action.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domains.contracts.risk_verification import VerifiedRisk
from app.domains.contracts.severity import compute_score, score_to_severity
from app.models.contracts import ContractRiskSeverity, RecommendationAction, RiskClassification


@dataclass
class Recommendation:
    action: RecommendationAction
    reason: str
    legal_basis: str | None
    commercial_reason: str | None
    priority: int  # 1 = act first


def recommend(verified_risk: VerifiedRisk) -> Recommendation:
    candidate = verified_risk.candidate
    severity = score_to_severity(compute_score(candidate.severity_inputs))

    if candidate.classification == RiskClassification.MISSING_PROTECTION:
        action = RecommendationAction.ADD
        reason = f"Рекомендуется добавить пункт: {candidate.title}."
    elif candidate.clause_index is None:
        # Structural finding without a specific clause to rewrite.
        action = RecommendationAction.NEGOTIATE
        reason = "Рекомендуется обсудить данный вопрос с контрагентом до подписания."
    elif severity in (ContractRiskSeverity.CRITICAL, ContractRiskSeverity.HIGH):
        action = RecommendationAction.REWRITE
        reason = f"Пункт рекомендуется переформулировать: {candidate.title}."
    elif severity == ContractRiskSeverity.MEDIUM:
        action = RecommendationAction.NEGOTIATE
        reason = f"Рекомендуется обсудить с контрагентом возможность корректировки: {candidate.title}."
    else:
        action = RecommendationAction.KEEP
        reason = "Существенного риска не выявлено; пункт можно сохранить в текущей редакции."

    priority = {
        ContractRiskSeverity.CRITICAL: 1, ContractRiskSeverity.HIGH: 2, ContractRiskSeverity.MEDIUM: 3,
        ContractRiskSeverity.LOW: 4, ContractRiskSeverity.INFO: 5,
    }[severity]

    return Recommendation(
        action=action,
        reason=reason,
        legal_basis=verified_risk.legal_basis,
        commercial_reason=candidate.why_it_matters,
        priority=priority,
    )
