from __future__ import annotations

from app.domains.legal_research.confidence import ConfidenceInputs, compute_citation_coverage, compute_confidence
from app.domains.legal_research.models import (
    ClaimImportance,
    ClaimVerificationStatus,
    ConfidenceLevel,
    ConflictType,
    Criticality,
    LegalClaim,
    LegalConflict,
    LegalIssue,
    MissingFact,
)
from app.domains.legal_research.review import review


def _claim(status, importance=ClaimImportance.CRITICAL, claim_type="rule", issue_id="1"):
    return LegalClaim(
        claim="c", claim_type=claim_type, importance=importance, citations=["x"],
        verification_status=status, issue_id=issue_id,
    )


# --- review() ---


def test_review_marks_unsupported_critical_claim():
    claims = [_claim(ClaimVerificationStatus.UNVERIFIED)]
    findings = review(issues=[], claims=claims, missing_facts=[], conflicts=[], temporal_warnings=[])

    assert claims[0].verification_status == ClaimVerificationStatus.UNSUPPORTED_CRITICAL
    assert findings.unsupported_critical_claims == ["c"]


def test_review_does_not_flag_verified_critical_claim():
    claims = [_claim(ClaimVerificationStatus.VERIFIED)]
    findings = review(issues=[], claims=claims, missing_facts=[], conflicts=[], temporal_warnings=[])
    assert findings.unsupported_critical_claims == []


def test_review_does_not_flag_unverified_non_critical_claim():
    claims = [_claim(ClaimVerificationStatus.UNVERIFIED, importance=ClaimImportance.SUPPORTING)]
    findings = review(issues=[], claims=claims, missing_facts=[], conflicts=[], temporal_warnings=[])
    assert findings.unsupported_critical_claims == []
    assert claims[0].verification_status == ClaimVerificationStatus.UNVERIFIED


def test_review_issues_look_complete_when_every_issue_has_a_claim():
    issue = LegalIssue(id="1", title="t", description="d", priority=1)
    claims = [_claim(ClaimVerificationStatus.VERIFIED, issue_id="1")]
    findings = review(issues=[issue], claims=claims, missing_facts=[], conflicts=[], temporal_warnings=[])
    assert findings.issues_look_complete is True


def test_review_issues_incomplete_when_issue_has_no_claim():
    issue = LegalIssue(id="1", title="t", description="d", priority=1)
    findings = review(issues=[issue], claims=[], missing_facts=[], conflicts=[], temporal_warnings=[])
    assert findings.issues_look_complete is False


def test_review_critical_facts_addressed_false_when_critical_missing_fact_present():
    missing = [MissingFact(question="q", criticality=Criticality.CRITICAL)]
    findings = review(issues=[], claims=[], missing_facts=missing, conflicts=[], temporal_warnings=[])
    assert findings.all_critical_facts_addressed is False


def test_review_critical_facts_addressed_true_when_only_optional_missing():
    missing = [MissingFact(question="q", criticality=Criticality.OPTIONAL)]
    findings = review(issues=[], claims=[], missing_facts=missing, conflicts=[], temporal_warnings=[])
    assert findings.all_critical_facts_addressed is True


def test_review_detects_conflicting_practice():
    conflict = LegalConflict(conflict_type=ConflictType.JURISPRUDENTIAL_CONFLICT, description="d", position_a="a", position_b="b")
    findings = review(issues=[], claims=[], missing_facts=[], conflicts=[conflict], temporal_warnings=[])
    assert findings.has_conflicting_practice is True


def test_review_flags_overreaching_conclusion():
    claim = _claim(ClaimVerificationStatus.VERIFIED, claim_type="conclusion")
    claim.claim = "Заказчик безусловно вправе отказаться от договора"
    findings = review(issues=[], claims=[claim], missing_facts=[], conflicts=[], temporal_warnings=[])
    assert findings.conclusion_overreaches is True


def test_review_does_not_flag_qualified_conclusion():
    claim = _claim(ClaimVerificationStatus.VERIFIED, claim_type="conclusion")
    claim.claim = "Заказчик, вероятно, вправе отказаться, однако вывод зависит от условий договора"
    findings = review(issues=[], claims=[claim], missing_facts=[], conflicts=[], temporal_warnings=[])
    assert findings.conclusion_overreaches is False


# --- compute_citation_coverage ---


def test_citation_coverage_full():
    claims = [_claim(ClaimVerificationStatus.VERIFIED), _claim(ClaimVerificationStatus.MOCK)]
    assert compute_citation_coverage(claims) == 1.0


def test_citation_coverage_partial():
    claims = [_claim(ClaimVerificationStatus.VERIFIED), _claim(ClaimVerificationStatus.UNVERIFIED)]
    assert compute_citation_coverage(claims) == 0.5


def test_citation_coverage_empty_claims():
    assert compute_citation_coverage([]) == 0.0


# --- compute_confidence ---


def test_confidence_high_with_strong_support():
    inputs = ConfidenceInputs(
        citation_coverage=1.0, evidence_count=4, unique_authority_count=2, has_conflicting_practice=False,
        missing_critical_facts=False, temporal_warnings_present=False, unsupported_critical_claims_present=False,
        conclusion_overreaches=False,
    )
    assert compute_confidence(inputs) == ConfidenceLevel.HIGH


def test_confidence_low_when_unsupported_critical_claim_present_overrides_everything():
    inputs = ConfidenceInputs(
        citation_coverage=1.0, evidence_count=10, unique_authority_count=5, has_conflicting_practice=False,
        missing_critical_facts=False, temporal_warnings_present=False, unsupported_critical_claims_present=True,
        conclusion_overreaches=False,
    )
    assert compute_confidence(inputs) == ConfidenceLevel.LOW


def test_confidence_low_when_missing_critical_facts():
    inputs = ConfidenceInputs(
        citation_coverage=1.0, evidence_count=10, unique_authority_count=5, has_conflicting_practice=False,
        missing_critical_facts=True, temporal_warnings_present=False, unsupported_critical_claims_present=False,
        conclusion_overreaches=False,
    )
    assert compute_confidence(inputs) == ConfidenceLevel.LOW


def test_confidence_medium_with_moderate_support():
    inputs = ConfidenceInputs(
        citation_coverage=0.6, evidence_count=1, unique_authority_count=1, has_conflicting_practice=False,
        missing_critical_facts=False, temporal_warnings_present=False, unsupported_critical_claims_present=False,
        conclusion_overreaches=False,
    )
    assert compute_confidence(inputs) == ConfidenceLevel.MEDIUM


def test_confidence_low_with_no_support():
    inputs = ConfidenceInputs(
        citation_coverage=0.0, evidence_count=0, unique_authority_count=0, has_conflicting_practice=True,
        missing_critical_facts=False, temporal_warnings_present=True, unsupported_critical_claims_present=False,
        conclusion_overreaches=True,
    )
    assert compute_confidence(inputs) == ConfidenceLevel.LOW
