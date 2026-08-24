"""Case Intelligence — party relationships pure functions. Synthetic data
only, no case_relationships.py function ever calls the DB or an LLM.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.domains.litigation.case_relationships import (
    CaseHypothesisInput,
    CasePartyRelationshipInput,
    build_party_relationship_findings,
    build_related_litigation_note,
    classify_relationship_timing,
)
from app.models.matters import HypothesisCategory, RelationshipType, RelationshipVerificationStatus


def test_timing_active_at_date_always_carries_the_knowledge_caveat():
    result = classify_relationship_timing(date(2023, 1, 1), None, date(2024, 9, 13))
    assert result.status == "active_at_date"
    assert "does not by itself establish actual knowledge" in result.caveat


def test_timing_not_yet_active():
    result = classify_relationship_timing(date(2025, 1, 1), None, date(2024, 9, 13))
    assert result.status == "not_yet_active"
    assert "had not yet begun" in result.caveat


def test_timing_ended_before():
    result = classify_relationship_timing(date(2020, 1, 1), date(2023, 12, 31), date(2024, 9, 13))
    assert result.status == "ended_before"
    assert "already ended" in result.caveat


def test_timing_unknown_when_no_dates_at_all():
    result = classify_relationship_timing(None, None, date(2024, 9, 13))
    assert result.status == "unknown_timing"
    assert "cannot be determined" in result.caveat


def test_timing_unknown_when_no_target_date():
    result = classify_relationship_timing(date(2023, 1, 1), None, None)
    assert result.status == "unknown_timing"


def test_related_litigation_note_never_claims_causation():
    note = build_related_litigation_note("А40-12345/2026")
    assert "А40-12345/2026" in note
    assert "не подтверждают" in note or "does not establish" in note
    assert "нуждается в деньгах" not in note
    assert "needs money" not in note


def test_related_litigation_note_without_case_number():
    note = build_related_litigation_note(None)
    assert "могут потребовать" in note


def test_party_relationship_findings_never_infer_knowledge_from_status_alone():
    relationship = CasePartyRelationshipInput(
        id=uuid.uuid4(), subject_party_id=uuid.uuid4(), subject_name="Слепнев П.Б.",
        related_party_id=uuid.uuid4(), related_party_name="ООО «БС ЭНЕРГО РЕГИОН»",
        relationship_type=RelationshipType.MEMBER, start_date=date(2024, 6, 1), end_date=None,
        verification_status=RelationshipVerificationStatus.UNVERIFIED, source_document_id=None, source_excerpt=None,
    )
    findings = build_party_relationship_findings(
        [relationship], reference_dates=[date(2024, 9, 13), date(2024, 10, 1)], hypotheses=[], document_titles={}
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.subject_name == "Слепнев П.Б."
    assert "может иметь значение" in finding.why_it_may_matter
    assert "does not by itself establish actual knowledge" in finding.timing_note
    # Default checklist used when no linked hypothesis supplies one.
    assert any("ЕГРЮЛ" in item for item in finding.what_is_still_needed)


def test_party_relationship_findings_use_linked_hypothesis_required_verification():
    relationship_id = uuid.uuid4()
    relationship = CasePartyRelationshipInput(
        id=relationship_id, subject_party_id=uuid.uuid4(), subject_name="Слепнев П.Б.",
        related_party_id=uuid.uuid4(), related_party_name="ООО «БС ЭНЕРГО РЕГИОН»",
        relationship_type=RelationshipType.MEMBER, start_date=date(2024, 6, 1), end_date=None,
        verification_status=RelationshipVerificationStatus.DOCUMENT_SUPPORTED, source_document_id=None, source_excerpt=None,
    )
    hypothesis = CaseHypothesisInput(
        id=uuid.uuid4(), category=HypothesisCategory.COUNSEL_HYPOTHESIS,
        statement="Заявитель имел доступ к корпоративной информации ответчика.",
        required_verification=["Запрос протоколов собраний участников"], related_relationship_id=relationship_id,
    )
    findings = build_party_relationship_findings([relationship], [], [hypothesis], {})
    assert findings[0].what_is_still_needed == ["Запрос протоколов собраний участников"]


def test_party_relationship_findings_capped_at_five():
    relationships = [
        CasePartyRelationshipInput(
            id=uuid.uuid4(), subject_party_id=uuid.uuid4(), subject_name=f"Person {i}",
            related_party_id=uuid.uuid4(), related_party_name="Entity", relationship_type=RelationshipType.DIRECTOR,
            start_date=None, end_date=None, verification_status=RelationshipVerificationStatus.UNVERIFIED,
            source_document_id=None, source_excerpt=None,
        )
        for i in range(8)
    ]
    findings = build_party_relationship_findings(relationships, [], [], {})
    assert len(findings) == 5


def test_findings_never_state_a_legal_verdict_about_the_relationship_itself():
    relationship = CasePartyRelationshipInput(
        id=uuid.uuid4(), subject_party_id=uuid.uuid4(), subject_name="Замарин М.Б.",
        related_party_id=uuid.uuid4(), related_party_name="ООО ГК «ЛЕДОВЫЙ СЕРВИС»",
        relationship_type=RelationshipType.DIRECTOR, start_date=date(2019, 2, 15), end_date=None,
        verification_status=RelationshipVerificationStatus.UNVERIFIED, source_document_id=None, source_excerpt=None,
    )
    findings = build_party_relationship_findings([relationship], [date(2024, 9, 13)], [], {})
    haystack = findings[0].why_it_may_matter.lower() + findings[0].timing_note.lower()
    for forbidden in ("установлено, что", "доказано, что", "заведомо знал", "is established that"):
        assert forbidden not in haystack
