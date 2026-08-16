from __future__ import annotations

from app.domains.contracts.report import build_report
from app.domains.contracts.risk_detection import RiskCandidate
from app.domains.contracts.risk_verification import VerifiedRisk
from app.domains.contracts.scoring import compute_overall_score, risk_summary_counts
from app.domains.contracts.severity import SeverityInputs
from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.domains.contracts.summary import build_summary
from app.domains.contracts.two_lawyer_review import ReviewedRisk
from app.domains.contracts.version_diff import diff_clauses, diff_risks
from app.models.contracts import (
    AgreementStatus,
    ContractRiskSeverity,
    ContractType,
    RiskCategory,
    RiskClassification,
    RiskType,
    RiskVerificationStatus,
)


def _reviewed_risk(title="t", category=RiskCategory.LEGAL, severity_inputs=None, clause_index=0, agreement=AgreementStatus.AGREED):
    candidate = RiskCandidate(
        detector="liability", risk_type=RiskType.UNLIMITED_LIABILITY, category=category,
        classification=RiskClassification.HIGH_RISK, title=title, description="d", why_it_matters="w",
        severity_inputs=severity_inputs or SeverityInputs(legal_impact=80, financial_impact=80, probability=60, scope=60,
            irreversibility=60),
        clause_index=clause_index,
    )
    verified = VerifiedRisk(
        candidate=candidate, verification_status=RiskVerificationStatus.MOCK, legal_basis="b",
        citations=["ст. 1"], confidence="medium", research_id="r", has_conflicting_practice=False,
    )
    return ReviewedRisk(verified_risk=verified, agreement_status=agreement)


# --- scoring ---


def test_compute_overall_score_deducts_per_severity():
    score = compute_overall_score([ContractRiskSeverity.CRITICAL, ContractRiskSeverity.HIGH])
    assert score == 100 - 25 - 12


def test_compute_overall_score_floors_at_zero():
    score = compute_overall_score([ContractRiskSeverity.CRITICAL] * 10)
    assert score == 0


def test_risk_summary_counts_includes_all_levels():
    counts = risk_summary_counts([ContractRiskSeverity.HIGH, ContractRiskSeverity.HIGH, ContractRiskSeverity.LOW])
    assert counts["high"] == 2
    assert counts["low"] == 1
    assert counts["critical"] == 0


# --- report ---


def test_build_report_buckets_by_severity():
    risks = [_reviewed_risk(title="a", severity_inputs=SeverityInputs(90, 90, 90, 90, 90))]
    clauses = ContractStructureExtractor().extract("1. Предмет\n\n1.1. Текст.\n")
    summary = build_summary(clauses, [])
    report = build_report(ContractType.SERVICE, summary, risks)

    assert len(report.critical_risks) == 1
    assert report.high_risks == []
    assert report.overall_score < 100


def test_build_report_separates_legal_and_commercial_findings():
    risks = [_reviewed_risk(title="legal-one", category=RiskCategory.LEGAL),
        _reviewed_risk(title="commercial-one", category=RiskCategory.COMMERCIAL)]
    clauses = ContractStructureExtractor().extract("1. Предмет\n\n1.1. Текст.\n")
    summary = build_summary(clauses, [])
    report = build_report(ContractType.SERVICE, summary, risks)

    assert len(report.legal_findings) == 1
    assert len(report.commercial_findings) == 1


def test_build_report_flags_requires_human_review():
    risks = [_reviewed_risk(agreement=AgreementStatus.DISAGREEMENT)]
    clauses = ContractStructureExtractor().extract("1. Предмет\n\n1.1. Текст.\n")
    summary = build_summary(clauses, [])
    report = build_report(ContractType.SERVICE, summary, risks)
    assert len(report.requires_human_review) == 1


def test_build_report_no_risks_yields_full_score():
    clauses = ContractStructureExtractor().extract("1. Предмет\n\n1.1. Текст.\n")
    summary = build_summary(clauses, [])
    report = build_report(ContractType.SERVICE, summary, [])
    assert report.overall_score == 100
    assert "0 критических" in report.executive_summary


# --- version diff ---


_V1 = "1. Предмет\n\n1.1. Старый текст.\n\n2. Оплата\n\n2.1. Оплата в течение 10 дней.\n"
_V2 = "1. Предмет\n\n1.1. Новый текст.\n\n3. Ответственность\n\n3.1. Ответственность ограничена.\n"


def test_diff_clauses_detects_added_and_removed():
    old_clauses = ContractStructureExtractor().extract(_V1)
    new_clauses = ContractStructureExtractor().extract(_V2)
    diff = diff_clauses(old_clauses, new_clauses)

    assert len(diff.removed) >= 1  # "Оплата" clauses gone
    assert len(diff.added) >= 1  # "Ответственность" clauses new


def test_diff_clauses_detects_changed_text_for_same_number():
    old_clauses = ContractStructureExtractor().extract(_V1)
    new_clauses = ContractStructureExtractor().extract(_V2)
    diff = diff_clauses(old_clauses, new_clauses)

    changed_numbers = {old.clause_number for old, new in diff.changed}
    assert "1.1" in changed_numbers


def test_diff_clauses_identical_versions_yield_no_changes():
    clauses = ContractStructureExtractor().extract(_V1)
    diff = diff_clauses(clauses, clauses)
    assert diff.added == []
    assert diff.removed == []
    assert diff.changed == []
    assert diff.unchanged_count == len(clauses)


def test_diff_risks_detects_new_and_resolved():
    old_risks = [_reviewed_risk(title="persisting"), _reviewed_risk(title="resolved")]
    new_risks = [_reviewed_risk(title="persisting"), _reviewed_risk(title="new-risk")]

    diff = diff_risks(old_risks, new_risks)

    assert [r.verified_risk.candidate.title for r in diff.new_risks] == ["new-risk"]
    assert [r.verified_risk.candidate.title for r in diff.resolved_risks] == ["resolved"]
    assert [r.verified_risk.candidate.title for r in diff.persisting_risks] == ["persisting"]
