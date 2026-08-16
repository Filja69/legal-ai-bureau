from __future__ import annotations

from datetime import date

from app.domains.legal_research.models import EvidenceItem, IssueType
from app.domains.legal_research.temporal_consistency import TemporalConsistencyChecker, classify_issue_type


def test_classify_issue_type_procedural_keyword():
    assert classify_issue_type("Срок исковой давности", "d") == IssueType.PROCEDURAL


def test_classify_issue_type_substantive_default():
    assert classify_issue_type("Право на отказ от договора", "d") == IssueType.SUBSTANTIVE


def test_temporal_consistency_flags_expired_version():
    item = EvidenceItem(
        source="s", citation="ст. 309", text="t", retrieval_score=1.0, retrieval_method=["exact"],
        metadata={"chunk_type": "law_version", "effective_from": "2024-01-01", "effective_to": "2025-01-01"},
    )
    warnings = TemporalConsistencyChecker().check([item], effective_at=date(2025, 6, 1))
    assert len(warnings) == 1
    assert "expired" in warnings[0]


def test_temporal_consistency_flags_not_yet_effective_version():
    item = EvidenceItem(
        source="s", citation="ст. 309", text="t", retrieval_score=1.0, retrieval_method=["exact"],
        metadata={"chunk_type": "law_version", "effective_from": "2025-01-01", "effective_to": None},
    )
    warnings = TemporalConsistencyChecker().check([item], effective_at=date(2024, 6, 1))
    assert len(warnings) == 1
    assert "after the requested date" in warnings[0]


def test_temporal_consistency_no_warning_when_within_window():
    item = EvidenceItem(
        source="s", citation="ст. 309", text="t", retrieval_score=1.0, retrieval_method=["exact"],
        metadata={"chunk_type": "law_version", "effective_from": "2024-01-01", "effective_to": "2025-01-01"},
    )
    warnings = TemporalConsistencyChecker().check([item], effective_at=date(2024, 6, 1))
    assert warnings == []


def test_temporal_consistency_skips_when_no_effective_at_requested():
    item = EvidenceItem(
        source="s", citation="ст. 309", text="t", retrieval_score=1.0, retrieval_method=["exact"],
        metadata={"chunk_type": "law_version", "effective_from": "2024-01-01", "effective_to": "2025-01-01"},
    )
    warnings = TemporalConsistencyChecker().check([item], effective_at=None)
    assert warnings == []
