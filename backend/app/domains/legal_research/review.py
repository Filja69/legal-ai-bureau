"""LegalResearchReviewer — brief §22-25. Deterministic checklist, not LLM
prose — the two-lawyer principle (LEGAL-AGENTS.md §5) applied to research:
this module never re-reads the reasoner's own self-assessment, only the
structured claims/conflicts/facts it produced, exactly like the existing
Legal Reviewer Agent pattern from Phase 1.
"""
from __future__ import annotations

from app.domains.legal_research.models import (
    ClaimImportance,
    ClaimVerificationStatus,
    ConflictType,
    Criticality,
    LegalClaim,
    LegalConflict,
    LegalIssue,
    MissingFact,
    ReviewFindings,
)

_OVERREACH_PHRASES = ("точно", "гарантированно", "100%", "безусловно", "стопроцентно", "однозначно да")


def review(
    issues: list[LegalIssue],
    claims: list[LegalClaim],
    missing_facts: list[MissingFact],
    conflicts: list[LegalConflict],
    temporal_warnings: list[str],
) -> ReviewFindings:
    """Mutates `claims` in place: any CRITICAL claim without a verified/mock
    citation is relabeled UNSUPPORTED_CRITICAL (brief §25's block signal) —
    the engine decides what to do with that (block finalization vs. surface
    a caveat), this function only detects it.
    """
    unsupported: list[str] = []
    for claim in claims:
        if claim.importance == ClaimImportance.CRITICAL and claim.verification_status not in (
            ClaimVerificationStatus.VERIFIED,
            ClaimVerificationStatus.MOCK,
        ):
            claim.verification_status = ClaimVerificationStatus.UNSUPPORTED_CRITICAL
            unsupported.append(claim.claim)

    issue_ids_with_claims = {c.issue_id for c in claims if c.issue_id}
    issues_look_complete = all(issue.id in issue_ids_with_claims for issue in issues) if issues else False

    all_critical_facts_addressed = not any(m.criticality == Criticality.CRITICAL for m in missing_facts)

    has_conflicting_practice = any(c.conflict_type == ConflictType.JURISPRUDENTIAL_CONFLICT for c in conflicts)

    conclusion_claims = [c for c in claims if c.claim_type == "conclusion"]
    conclusion_overreaches = any(
        phrase in c.claim.lower() for c in conclusion_claims for phrase in _OVERREACH_PHRASES
    )

    notes: list[str] = []
    if unsupported:
        notes.append(f"{len(unsupported)} critical claim(s) lack a verified citation.")
    if not issues_look_complete:
        notes.append("At least one identified issue has no supporting claim.")
    if not all_critical_facts_addressed:
        notes.append("Critical facts remain unknown.")
    if has_conflicting_practice:
        notes.append("Retrieved court practice is not uniform on this question.")
    if temporal_warnings:
        notes.append("Temporal validity check flagged possible redaction mismatches.")
    if conclusion_overreaches:
        notes.append("Conclusion language may overstate certainty.")

    return ReviewFindings(
        all_critical_facts_addressed=all_critical_facts_addressed,
        issues_look_complete=issues_look_complete,
        unsupported_critical_claims=unsupported,
        has_conflicting_practice=has_conflicting_practice,
        outdated_redaction_used=bool(temporal_warnings),
        conclusion_overreaches=conclusion_overreaches,
        notes=notes,
    )
