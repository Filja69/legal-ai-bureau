"""Legal Theory Layer authority enrichment (P2 §5/§6/§10/§11) — pure,
zero-LLM/zero-DB transformation of an already-computed LegalResearchResult
into the report-facing shape (applicable rules, supporting/adverse case law,
unverified authorities, adverse arguments, unresolved questions). Exercised
directly against hand-built LegalClaim/CaseLawRelevance/LegalConflict
objects so the classification logic itself is pinned down precisely, without
needing a full retrieval pipeline.
"""
from __future__ import annotations

from app.domains.legal_research.models import (
    CaseLawRelevance,
    ClaimImportance,
    ClaimVerificationStatus,
    ConfidenceLevel,
    ConflictType,
    Criticality,
    LegalClaim,
    LegalConflict,
    LegalResearchResult,
    MissingFact,
)
from app.domains.litigation.pipeline import (
    _build_adverse_arguments,
    _build_applicable_rules,
    _build_case_law_sections,
    _build_unresolved_questions,
    _build_unverified_authorities,
)


def _rule_claim(citation: str, status: ClaimVerificationStatus) -> LegalClaim:
    return LegalClaim(
        claim=f"{citation}: some rule text",
        claim_type="rule",
        importance=ClaimImportance.CRITICAL,
        citations=[citation] if status != ClaimVerificationStatus.UNVERIFIED else [],
        verification_status=status,
        issue_id="1",
    )


def _case_law_claim(case_number: str, status: ClaimVerificationStatus) -> LegalClaim:
    return LegalClaim(
        claim=f"{case_number}: some decision text",
        claim_type="case_law",
        importance=ClaimImportance.CRITICAL,
        citations=[case_number] if status != ClaimVerificationStatus.UNVERIFIED else [],
        verification_status=status,
        issue_id="1",
    )


def _relevance(case_number: str, stance: str, assessed: bool = True) -> CaseLawRelevance:
    return CaseLawRelevance(
        case_number=case_number, court_level_label="АС г. Москвы", decision_date="2024-01-01", outcome="granted",
        factual_similarity="high", legal_issue_similarity="high", procedural_posture_note="note",
        stance=stance, assessed=assessed,
    )


# --- _build_applicable_rules ---


def test_applicable_rules_includes_verified_and_mock_excludes_unverified():
    claims = [
        _rule_claim("ст. 432 ГК РФ", ClaimVerificationStatus.VERIFIED),
        _rule_claim("ст. 434 ГК РФ", ClaimVerificationStatus.MOCK),
        _rule_claim("ст. 99999 ГК РФ", ClaimVerificationStatus.UNVERIFIED),
    ]
    rules = _build_applicable_rules(claims)

    citations = {r.citation for r in rules}
    assert citations == {"ст. 432 ГК РФ", "ст. 434 ГК РФ"}
    verified = next(r for r in rules if r.citation == "ст. 432 ГК РФ")
    assert verified.verification_status == "verified"
    assert "официальный" in verified.provenance
    mock = next(r for r in rules if r.citation == "ст. 434 ГК РФ")
    assert mock.verification_status == "mock"
    assert "mock" in mock.provenance.lower() or "демонстрационные" in mock.provenance


# --- _build_unverified_authorities ---


def test_unverified_authorities_surfaces_rule_and_case_law_fabrications():
    claims = [
        _rule_claim("ст. 432 ГК РФ", ClaimVerificationStatus.VERIFIED),
        _rule_claim("ст. 99999 ГК РФ", ClaimVerificationStatus.UNVERIFIED),
        _case_law_claim("А99-9999/2099", ClaimVerificationStatus.UNVERIFIED),
    ]
    unverified = _build_unverified_authorities(claims)

    assert len(unverified) == 2
    attempted = {u.attempted_citation for u in unverified}
    assert attempted == {"ст. 99999 ГК РФ", "А99-9999/2099"}
    types = {u.claim_type for u in unverified}
    assert types == {"rule", "case_law"}
    assert all("не учитывается" in u.reason for u in unverified)


# --- _build_case_law_sections ---


def test_case_law_sections_split_by_stance_and_dedupe():
    claims = [
        _case_law_claim("А40-1/2024", ClaimVerificationStatus.VERIFIED),
        _case_law_claim("А40-1/2024", ClaimVerificationStatus.VERIFIED),  # same decision retrieved twice
        _case_law_claim("А40-2/2024", ClaimVerificationStatus.VERIFIED),
        _case_law_claim("А40-3/2024", ClaimVerificationStatus.VERIFIED),
        _case_law_claim("А40-4/2024", ClaimVerificationStatus.MOCK),
        _case_law_claim("А40-5/2024", ClaimVerificationStatus.UNVERIFIED),  # must never appear anywhere below
    ]
    relevance_by_case = {
        "А40-1/2024": _relevance("А40-1/2024", "supports"),
        "А40-2/2024": _relevance("А40-2/2024", "against"),
        "А40-3/2024": _relevance("А40-3/2024", "distinguishable"),
        # А40-4/2024 deliberately has no relevance entry (assessment failed/mock) — uncharacterized.
    }

    supporting, adverse, uncharacterized = _build_case_law_sections(claims, relevance_by_case)

    assert [c.case_number for c in supporting] == ["А40-1/2024"]  # deduped, only one entry
    assert {c.case_number for c in adverse} == {"А40-2/2024", "А40-3/2024"}
    assert {c.case_number for c in uncharacterized} == {"А40-4/2024"}
    assert all("А40-5/2024" != c.case_number for group in (supporting, adverse, uncharacterized) for c in group)


def test_case_law_sections_unassessed_relevance_goes_to_uncharacterized():
    claims = [_case_law_claim("А40-9/2024", ClaimVerificationStatus.VERIFIED)]
    relevance_by_case = {"А40-9/2024": _relevance("А40-9/2024", "unclear", assessed=False)}

    supporting, adverse, uncharacterized = _build_case_law_sections(claims, relevance_by_case)

    assert supporting == []
    assert adverse == []
    assert [c.case_number for c in uncharacterized] == ["А40-9/2024"]


# --- _build_adverse_arguments ---


def test_adverse_arguments_combines_counterarguments_and_conflicts():
    result = LegalResearchResult(
        executive_conclusion="c", confidence=ConfidenceLevel.MEDIUM,
        counterarguments=["ст. 450 ГК РФ: расторжение договора при существенном нарушении"],
        conflicts=[
            LegalConflict(
                conflict_type=ConflictType.JURISPRUDENTIAL_CONFLICT, description="Практика судов расходится",
                position_a="Суд А считает требование обоснованным", position_b="Суд Б считает требование преждевременным",
                implication="Требует дополнительной проверки практики.",
            )
        ],
    )
    arguments = _build_adverse_arguments(result)

    assert len(arguments) == 2
    assert "ст. 450 ГК РФ" in arguments[0]
    assert "Практика судов расходится" in arguments[1]
    assert "Суд А считает" in arguments[1]
    assert "Требует дополнительной проверки" in arguments[1]


# --- _build_unresolved_questions ---


def test_unresolved_questions_dedupes_missing_facts_and_escalation_reasons():
    result = LegalResearchResult(
        executive_conclusion="c", confidence=ConfidenceLevel.LOW,
        missing_facts=[
            MissingFact(question="Была ли договоренность оформлена позднее нотариально?", criticality=Criticality.CRITICAL),
            MissingFact(question="Была ли договоренность оформлена позднее нотариально?", criticality=Criticality.CRITICAL),
        ],
        escalation_reasons=["Critical legal claim lacks a verified citation."],
    )
    questions = _build_unresolved_questions(result)

    assert questions == [
        "Была ли договоренность оформлена позднее нотариально?",
        "Critical legal claim lacks a verified citation.",
    ]
