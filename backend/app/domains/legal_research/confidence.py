"""ConfidenceCalculator — brief §32-33. Deterministic, not LLM-generated.

Confidence answers "how well-supported is *our* analysis", never a
probability of winning in court — no statistical methodology backs a
number like that, so this module never produces one (brief §33).

Hard rules take priority over the composite score: an unsupported critical
claim caps confidence at LOW no matter how good everything else looks —
matching the brief's BLOCK_FINALIZATION intent (§25) at the confidence
layer too, not just the status flag.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domains.legal_research.models import ClaimVerificationStatus, ConfidenceLevel, EvidenceItem, LegalClaim, ReviewFindings

_VERIFIED_STATUSES = (ClaimVerificationStatus.VERIFIED, ClaimVerificationStatus.MOCK)


def compute_citation_coverage(claims: list[LegalClaim]) -> float:
    """brief §23 — substantive claims (rule/conclusion, not every intermediate
    statement) that carry a verified-or-mock citation, as a fraction of all
    substantive claims. Never inflated by counting claims that need no
    citation (there are none in this model — everything substantive here is
    either a cited rule or a conclusion built from cited rules).
    """
    if not claims:
        return 0.0
    verified = sum(1 for c in claims if c.verification_status in _VERIFIED_STATUSES)
    return verified / len(claims)


@dataclass
class ConfidenceInputs:
    citation_coverage: float
    evidence_count: int
    unique_authority_count: int
    has_conflicting_practice: bool
    missing_critical_facts: bool
    temporal_warnings_present: bool
    unsupported_critical_claims_present: bool
    conclusion_overreaches: bool


def compute_confidence(inputs: ConfidenceInputs) -> ConfidenceLevel:
    # Hard caps first — these override the composite score entirely.
    if inputs.unsupported_critical_claims_present:
        return ConfidenceLevel.LOW
    if inputs.missing_critical_facts:
        return ConfidenceLevel.LOW

    score = 0
    if inputs.citation_coverage >= 0.8:
        score += 2
    elif inputs.citation_coverage >= 0.5:
        score += 1

    if inputs.evidence_count >= 3:
        score += 1
    if inputs.unique_authority_count >= 2:
        score += 1
    if not inputs.has_conflicting_practice:
        score += 1
    if not inputs.temporal_warnings_present:
        score += 1
    if inputs.conclusion_overreaches:
        score -= 1

    if score >= 5:
        return ConfidenceLevel.HIGH
    if score >= 3:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def inputs_from_pipeline(
    claims_citation_coverage: float,
    evidence: list[EvidenceItem],
    review_findings: ReviewFindings,
    temporal_warnings: list[str],
) -> ConfidenceInputs:
    return ConfidenceInputs(
        citation_coverage=claims_citation_coverage,
        evidence_count=len({e.document_id for e in evidence if e.document_id}),
        unique_authority_count=len({e.authority for e in evidence if e.authority}),
        has_conflicting_practice=review_findings.has_conflicting_practice,
        missing_critical_facts=not review_findings.all_critical_facts_addressed,
        temporal_warnings_present=bool(temporal_warnings),
        unsupported_critical_claims_present=bool(review_findings.unsupported_critical_claims),
        conclusion_overreaches=review_findings.conclusion_overreaches,
    )
