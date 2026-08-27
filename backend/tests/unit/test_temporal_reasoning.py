"""Case temporal reasoning — a generic date-comparison layer, tested purely
on synthetic dates unrelated to any real case.
"""
from __future__ import annotations

from datetime import date

from app.domains.litigation.temporal_reasoning import analyze_temporal_issues, extract_document_own_date

_NO_TRACKING_ARGS = {"demand_tracking_present": False, "demand_final_status": "UNKNOWN"}


def test_extract_document_own_date_returns_last_date_in_text():
    text = "Договор от 01.02.2024. Представитель по доверенности Петров П.П.\n15.06.2025"
    assert extract_document_own_date(text) == date(2025, 6, 15)


def test_extract_document_own_date_returns_none_when_absent():
    assert extract_document_own_date("no dates here at all") is None


def test_no_issues_when_all_dates_are_consistent():
    issues = analyze_temporal_issues(
        earliest_interest_start=date(2025, 6, 1),
        latest_maturity_date=date(2025, 1, 1),
        demand_date=date(2025, 3, 1),
        claim_document_date=date(2025, 7, 1),
        **_NO_TRACKING_ARGS,
    )
    assert issues == []


def test_interest_before_demand_flagged():
    issues = analyze_temporal_issues(
        earliest_interest_start=date(2025, 1, 1),
        latest_maturity_date=None,
        demand_date=date(2025, 3, 1),
        claim_document_date=None,
        **_NO_TRACKING_ARGS,
    )
    assert len(issues) == 1
    assert issues[0].issue_type == "interest_before_demand"
    assert issues[0].dates == {"interest_start": date(2025, 1, 1), "demand_date": date(2025, 3, 1)}


def test_interest_before_maturity_flagged():
    issues = analyze_temporal_issues(
        earliest_interest_start=date(2025, 1, 1),
        latest_maturity_date=date(2025, 6, 1),
        demand_date=None,
        claim_document_date=None,
        **_NO_TRACKING_ARGS,
    )
    assert any(i.issue_type == "interest_before_maturity" for i in issues)


def test_claim_filed_before_maturity_flagged():
    issues = analyze_temporal_issues(
        earliest_interest_start=None,
        latest_maturity_date=date(2025, 12, 1),
        demand_date=None,
        claim_document_date=date(2025, 6, 1),
        **_NO_TRACKING_ARGS,
    )
    assert any(i.issue_type == "claim_filed_before_maturity" for i in issues)


def test_demand_returned_is_flagged_only_when_tracking_present():
    issues = analyze_temporal_issues(
        earliest_interest_start=None,
        latest_maturity_date=None,
        demand_date=date(2025, 3, 1),
        claim_document_date=None,
        demand_tracking_present=True,
        demand_final_status="RETURNED",
    )
    assert any(i.issue_type == "demand_not_confirmed_received" for i in issues)


def test_demand_unknown_status_without_tracking_is_not_flagged():
    """No tracking data at all is not itself suspicious — most demand
    letters are sent without a tracked-mail exhibit."""
    issues = analyze_temporal_issues(
        earliest_interest_start=None,
        latest_maturity_date=None,
        demand_date=date(2025, 3, 1),
        claim_document_date=None,
        demand_tracking_present=False,
        demand_final_status="UNKNOWN",
    )
    assert issues == []


def test_demand_delivered_is_not_flagged():
    issues = analyze_temporal_issues(
        earliest_interest_start=None,
        latest_maturity_date=None,
        demand_date=date(2025, 3, 1),
        claim_document_date=None,
        demand_tracking_present=True,
        demand_final_status="DELIVERED",
    )
    assert issues == []
