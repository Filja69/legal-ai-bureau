"""ContractReviewReport — brief §41. Pure aggregation/formatting over
already-computed structures (clauses, two-lawyer risks, recommendations,
alternative clauses) — this module invents nothing, it only organizes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.contracts.recommendations import Recommendation, recommend
from app.domains.contracts.scoring import compute_overall_score, risk_summary_counts
from app.domains.contracts.severity import compute_score, score_to_severity
from app.domains.contracts.summary import ContractSummary
from app.domains.contracts.two_lawyer_review import ReviewedRisk
from app.models.contracts import AgreementStatus, ContractRiskSeverity, ContractType


@dataclass
class RiskReportEntry:
    reviewed_risk: ReviewedRisk
    severity: ContractRiskSeverity
    recommendation: Recommendation


@dataclass
class ContractReviewReport:
    executive_summary: str
    contract_type: ContractType
    overview: ContractSummary
    critical_risks: list[RiskReportEntry] = field(default_factory=list)
    high_risks: list[RiskReportEntry] = field(default_factory=list)
    medium_risks: list[RiskReportEntry] = field(default_factory=list)
    low_risks: list[RiskReportEntry] = field(default_factory=list)
    info_risks: list[RiskReportEntry] = field(default_factory=list)
    legal_findings: list[RiskReportEntry] = field(default_factory=list)
    commercial_findings: list[RiskReportEntry] = field(default_factory=list)
    requires_human_review: list[RiskReportEntry] = field(default_factory=list)
    overall_score: int = 100
    risk_summary: dict[str, int] = field(default_factory=dict)


def build_report(contract_type: ContractType, overview: ContractSummary, reviewed_risks: list[ReviewedRisk]) -> ContractReviewReport:
    entries = []
    for rr in reviewed_risks:
        severity = score_to_severity(compute_score(rr.verified_risk.candidate.severity_inputs))
        entries.append(RiskReportEntry(reviewed_risk=rr, severity=severity, recommendation=recommend(rr.verified_risk)))

    by_severity: dict[ContractRiskSeverity, list[RiskReportEntry]] = {level: [] for level in ContractRiskSeverity}
    for entry in entries:
        by_severity[entry.severity].append(entry)

    legal_findings = [e for e in entries if e.reviewed_risk.verified_risk.candidate.category.value == "legal"]
    commercial_findings = [e for e in entries if e.reviewed_risk.verified_risk.candidate.category.value == "commercial"]
    requires_human_review = [e for e in entries if e.reviewed_risk.agreement_status != AgreementStatus.AGREED]

    severities = [e.severity for e in entries]
    overall_score = compute_overall_score(severities)

    critical_count = len(by_severity[ContractRiskSeverity.CRITICAL])
    high_count = len(by_severity[ContractRiskSeverity.HIGH])
    executive_summary = (
        f"Выявлено {len(entries)} потенциальных проблем: "
        f"{critical_count} критических, {high_count} высоких. "
        f"Общая оценка договора: {overall_score}/100."
    )

    return ContractReviewReport(
        executive_summary=executive_summary,
        contract_type=contract_type,
        overview=overview,
        critical_risks=by_severity[ContractRiskSeverity.CRITICAL],
        high_risks=by_severity[ContractRiskSeverity.HIGH],
        medium_risks=by_severity[ContractRiskSeverity.MEDIUM],
        low_risks=by_severity[ContractRiskSeverity.LOW],
        info_risks=by_severity[ContractRiskSeverity.INFO],
        legal_findings=legal_findings,
        commercial_findings=commercial_findings,
        requires_human_review=requires_human_review,
        overall_score=overall_score,
        risk_summary=risk_summary_counts(severities),
    )
