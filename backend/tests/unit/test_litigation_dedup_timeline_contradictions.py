"""Fact dedup, timeline, contradiction detection, evidence matrix —
Phase 9.3 brief §9/§10/§11/§12/§13/§14.
"""
from __future__ import annotations

import uuid

from app.domains.litigation.contradiction_detector import detect_contradictions
from app.domains.litigation.evidence_matrix import EvidenceStrength, build_evidence_matrix
from app.domains.litigation.fact_dedup import CanonicalFact, deduplicate_facts
from app.domains.litigation.fact_extractor import FactCandidate, FactEvidenceCandidate
from app.domains.litigation.timeline_builder import build_timeline
from app.models.matters import DateType, FactType


def _evidence(document_id=None, excerpt="context") -> FactEvidenceCandidate:
    return FactEvidenceCandidate(
        document_id=document_id or uuid.uuid4(), document_title="Doc", chunk_id=uuid.uuid4(),
        page_number=1, section_path=None, excerpt=excerpt,
    )


def _candidate(fact_type: FactType, value: str, statement: str = "stmt", document_id=None, excerpt="context") -> FactCandidate:
    return FactCandidate(fact_type=fact_type, statement=statement, normalized_value=value, evidence=_evidence(document_id, excerpt))


# --- Dedup (brief §9) ---


def test_dedup_merges_identical_values_from_different_documents():
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    candidates = [
        _candidate(FactType.DATE, "2026-03-10", document_id=doc_a),
        _candidate(FactType.DATE, "2026-03-10", document_id=doc_b),
    ]
    canonical = deduplicate_facts(candidates)
    assert len(canonical) == 1
    assert canonical[0].corroboration_count == 2


def test_dedup_keeps_different_values_separate():
    candidates = [_candidate(FactType.DATE, "2026-03-10"), _candidate(FactType.DATE, "2026-03-12")]
    canonical = deduplicate_facts(candidates)
    assert len(canonical) == 2


def test_dedup_never_merges_across_fact_types():
    candidates = [_candidate(FactType.DATE, "500"), _candidate(FactType.AMOUNT, "500")]
    canonical = deduplicate_facts(candidates)
    assert len(canonical) == 2


def test_corroboration_count_counts_distinct_documents_not_evidence_rows():
    doc_a = uuid.uuid4()
    candidates = [_candidate(FactType.DATE, "2026-03-10", document_id=doc_a), _candidate(FactType.DATE, "2026-03-10", document_id=doc_a)]
    canonical = deduplicate_facts(candidates)
    assert canonical[0].corroboration_count == 1  # same document twice != two independent sources


# --- Timeline (brief §10/§11) ---


def test_timeline_sorts_chronologically():
    facts = [
        CanonicalFact(FactType.DATE, "s1", "2026-03-15", [_evidence()]),
        CanonicalFact(FactType.DATE, "s2", "2026-01-01", [_evidence()]),
        CanonicalFact(FactType.DATE, "s3", "2026-02-10", [_evidence()]),
    ]
    events = build_timeline(facts)
    assert [e.event_date.isoformat() for e in events] == ["2026-01-01", "2026-02-10", "2026-03-15"]


def test_timeline_marks_dates_exact():
    facts = [CanonicalFact(FactType.DATE, "s", "2026-03-15", [_evidence()])]
    events = build_timeline(facts)
    assert events[0].date_type == DateType.EXACT


def test_timeline_infers_event_type_from_evidence_excerpt():
    facts = [CanonicalFact(FactType.DATE, "s", "2026-03-15", [_evidence(excerpt="Товар передан по акту приёмки")])]
    events = build_timeline(facts)
    assert events[0].event_type == "acceptance"


# --- Contradictions (brief §14) ---


def test_detects_date_mismatch_for_same_event_type():
    facts = [
        CanonicalFact(FactType.DATE, "s1", "2026-03-10", [_evidence(excerpt="доставка товара произведена")]),
        CanonicalFact(FactType.DATE, "s2", "2026-03-12", [_evidence(excerpt="поставка совершена")]),
    ]
    contradictions = detect_contradictions(facts)
    assert len(contradictions) == 1
    assert contradictions[0].contradiction_type.value == "date_mismatch"


def test_no_date_contradiction_for_unrelated_event_types():
    facts = [
        CanonicalFact(FactType.DATE, "s1", "2026-01-01", [_evidence(excerpt="договор подписан сторонами")]),
        CanonicalFact(FactType.DATE, "s2", "2026-03-01", [_evidence(excerpt="произведена оплата по счету")]),
    ]
    contradictions = detect_contradictions(facts)
    assert contradictions == []


def test_detects_amount_mismatch_within_same_order_of_magnitude():
    facts = [
        CanonicalFact(FactType.AMOUNT, "s1", "500000.00", [_evidence()]),
        CanonicalFact(FactType.AMOUNT, "s2", "450000.00", [_evidence()]),
    ]
    contradictions = detect_contradictions(facts)
    assert len(contradictions) == 1
    assert contradictions[0].contradiction_type.value == "amount_mismatch"


def test_no_amount_contradiction_for_wildly_different_magnitudes():
    facts = [
        CanonicalFact(FactType.AMOUNT, "s1", "500000.00", [_evidence()]),
        CanonicalFact(FactType.AMOUNT, "s2", "1000.00", [_evidence()]),
    ]
    contradictions = detect_contradictions(facts)
    assert contradictions == []


# --- Evidence matrix (brief §12/§13) ---


def test_strong_when_corroborated_and_not_contradicted():
    fact = CanonicalFact(FactType.DATE, "s", "2026-01-01", [_evidence(), _evidence()])
    rows = build_evidence_matrix([fact], [])
    assert rows[0].strength == EvidenceStrength.STRONG


def test_moderate_when_single_source():
    fact = CanonicalFact(FactType.DATE, "s", "2026-01-01", [_evidence()])
    rows = build_evidence_matrix([fact], [])
    assert rows[0].strength == EvidenceStrength.MODERATE


def test_conflicted_when_contradicted_even_if_corroborated():
    from app.domains.litigation.contradiction_detector import ContradictionCandidate
    from app.models.matters import ContradictionType

    fact_a = CanonicalFact(FactType.DATE, "s1", "2026-03-10", [_evidence(), _evidence()])
    fact_b = CanonicalFact(FactType.DATE, "s2", "2026-03-12", [_evidence()])
    contradiction = ContradictionCandidate(ContradictionType.DATE_MISMATCH, fact_a, fact_b, "mismatch")
    rows = build_evidence_matrix([fact_a, fact_b], [contradiction])
    assert all(row.strength == EvidenceStrength.CONFLICTED for row in rows)


def test_matrix_never_produces_a_fabricated_percentage():
    fact = CanonicalFact(FactType.DATE, "s", "2026-01-01", [_evidence()])
    rows = build_evidence_matrix([fact], [])
    assert isinstance(rows[0].strength.value, str)
    assert "%" not in rows[0].strength.value
