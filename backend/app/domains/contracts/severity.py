"""Deterministic risk severity scoring — brief §20-21.

Severity is never assigned directly by an LLM or a detector's gut feeling —
every detector produces the same five 0-100 inputs (legal_impact,
financial_impact, probability, scope, irreversibility) and this module maps
them to a severity band through one reproducible formula. Re-running the
same detector against the same clause always yields the same severity.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.contracts import ContractRiskSeverity

_WEIGHTS = {
    "legal_impact": 0.30,
    "financial_impact": 0.30,
    "probability": 0.20,
    "scope": 0.10,
    "irreversibility": 0.10,
}


@dataclass
class SeverityInputs:
    legal_impact: int  # 0-100
    financial_impact: int
    probability: int
    scope: int
    irreversibility: int

    def __post_init__(self) -> None:
        for field_name in _WEIGHTS:
            value = getattr(self, field_name)
            if not 0 <= value <= 100:
                raise ValueError(f"{field_name} must be within [0, 100], got {value}")


def compute_score(inputs: SeverityInputs) -> int:
    return round(sum(getattr(inputs, name) * weight for name, weight in _WEIGHTS.items()))


def score_to_severity(score: int) -> ContractRiskSeverity:
    if score >= 76:
        return ContractRiskSeverity.CRITICAL
    if score >= 51:
        return ContractRiskSeverity.HIGH
    if score >= 31:
        return ContractRiskSeverity.MEDIUM
    if score >= 10:
        return ContractRiskSeverity.LOW
    return ContractRiskSeverity.INFO
