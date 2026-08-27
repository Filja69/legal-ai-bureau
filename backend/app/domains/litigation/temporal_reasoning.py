"""Case Temporal Reasoning (P0 reasoning primitive). A generic comparison
layer over dates already extracted by other modules — never extracts text
itself, never resolves a legal conclusion. Every issue this module reports
is a TIMING OBSERVATION requiring legal verification, phrased with explicit
caveats, per the case_reasoning_graph discipline this package follows
throughout (see master_report.py's module docstring).

Nothing here is specific to any one case: the inputs are generic dates
(earliest claimed-interest accrual start, contract maturity, demand
delivery outcome) that any Russian civil claim can produce.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_DOCUMENT_OWN_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def extract_document_own_date(text: str) -> date | None:
    """Best-effort: the last standalone numeric date in a document's own
    text — typically its signature/dispatch date. This is the document's
    OWN stated date, never a certified court-filing/registration date;
    callers must caveat it as such. Returns None rather than guessing when
    no numeric date is present.
    """
    matches = list(_DOCUMENT_OWN_DATE.finditer(text))
    if not matches:
        return None
    day, month, year = matches[-1].groups()
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


@dataclass
class TemporalIssue:
    # "interest_before_demand" | "demand_not_confirmed_received" |
    # "interest_before_maturity" | "claim_filed_before_maturity"
    issue_type: str
    dates: dict[str, date]


def analyze_temporal_issues(
    *,
    earliest_interest_start: date | None,
    latest_maturity_date: date | None,
    demand_date: date | None,
    demand_tracking_present: bool,
    demand_final_status: str,
    claim_document_date: date | None,
) -> list[TemporalIssue]:
    issues: list[TemporalIssue] = []

    if earliest_interest_start is not None and demand_date is not None and earliest_interest_start < demand_date:
        issues.append(
            TemporalIssue("interest_before_demand", {"interest_start": earliest_interest_start, "demand_date": demand_date})
        )

    if demand_tracking_present and demand_final_status in ("RETURNED", "NOTICE_LEFT") and demand_date is not None:
        issues.append(TemporalIssue("demand_not_confirmed_received", {"demand_date": demand_date}))

    if earliest_interest_start is not None and latest_maturity_date is not None and earliest_interest_start < latest_maturity_date:
        issues.append(
            TemporalIssue("interest_before_maturity", {"interest_start": earliest_interest_start, "maturity": latest_maturity_date})
        )

    if claim_document_date is not None and latest_maturity_date is not None and claim_document_date < latest_maturity_date:
        issues.append(
            TemporalIssue("claim_filed_before_maturity", {"claim_date": claim_document_date, "maturity": latest_maturity_date})
        )

    return issues
