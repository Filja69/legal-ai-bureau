"""Overall contract score — brief §13/§41 dashboard number (0-100). Deterministic
deduction per risk severity, floored at 0 — never an LLM-guessed number.
"""
from __future__ import annotations

from app.models.contracts import ContractRiskSeverity

_DEDUCTION = {
    ContractRiskSeverity.CRITICAL: 25,
    ContractRiskSeverity.HIGH: 12,
    ContractRiskSeverity.MEDIUM: 5,
    ContractRiskSeverity.LOW: 2,
    ContractRiskSeverity.INFO: 0,
}


def compute_overall_score(severities: list[ContractRiskSeverity]) -> int:
    deduction = sum(_DEDUCTION[s] for s in severities)
    return max(0, 100 - deduction)


def risk_summary_counts(severities: list[ContractRiskSeverity]) -> dict[str, int]:
    counts = {s.value: 0 for s in ContractRiskSeverity}
    for s in severities:
        counts[s.value] += 1
    return counts
