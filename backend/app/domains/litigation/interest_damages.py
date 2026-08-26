"""Interest/damages timeline analysis (P0 reasoning primitive). Extracts a
claimed interest/damages figure and its calculation period from CLAIM-role
document text, using the standard Russian legal phrasing for statutory
interest for use of another's funds ("проценты за пользование чужими
денежными средствами" — Art. 395 GK RF is the generic statutory basis for
this phrase across essentially any Russian civil claim, not specific to any
one case), then compares the claimed period's start date against the
earliest payment date and any numerically-parseable contract maturity date
already extracted by contract_forensics.py.

Two independent phrasing variants are matched (amount-then-label, and
label-then-amount-in-размере) since Russian pleadings vary in word order —
this is a generalization concern, not a case-specific one: overfitting to a
single real document's exact word order is exactly what regression tests
for this module must catch (see test_interest_damages.py).

Never concludes a legal outcome. If the maturity date can't be reliably
parsed (e.g. a wordy Russian date, or simply absent), this module reports
that plainly rather than guessing — the caller (master_report.py) always
labels the resulting finding as requiring legal research, never a resolved
legal position.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Variant 1: amount stated before the "проценты ... за пользование чужими
# денежными средствами" label (e.g. "2 218 287,97 руб. проценты за
# пользование чужими денежными средствами").
_INTEREST_AMOUNT_BEFORE_LABEL = re.compile(
    r"(\d[\d\s\xa0 ]*(?:[.,]\d{2})?)\s*руб[а-яё.]*\s*[-—]?\s*процент[а-яё]*\s+за\s+пользование\s+чужими\s+"
    r"денежными\s+средствами",
    re.IGNORECASE,
)
# Variant 2: amount stated after the label, introduced by "в размере"
# (e.g. "проценты за пользование чужими денежными средствами в размере
# 2 218 287,97 руб.").
_INTEREST_AMOUNT_AFTER_LABEL = re.compile(
    r"процент[а-яё]*\s+за\s+пользование\s+чужими\s+денежными\s+средствами[^.]{0,40}?"
    r"в\s+размере\s+(\d[\d\s\xa0 ]*(?:[.,]\d{2})?)\s*руб",
    re.IGNORECASE,
)
_INTEREST_PERIOD_PATTERN = re.compile(
    r"за\s+период\s+с\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+по\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    re.IGNORECASE,
)
_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")


def _parse_numeric_date(raw: str) -> date | None:
    match = _NUMERIC_DATE.search(raw)
    if not match:
        return None
    day, month, year = match.groups()
    if len(year) == 2:
        year = f"20{year}"
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _normalize_amount(raw: str) -> str | None:
    cleaned = raw.replace(" ", "").replace("\xa0", "").replace(" ", "")
    match = re.match(r"(\d+)(?:[.,](\d{2}))?", cleaned)
    if not match:
        return None
    fractional = match.group(2) or "00"
    return f"{int(match.group(1))}.{fractional}"


@dataclass
class InterestClaimResult:
    claimed_amount: str | None
    period_start: date | None
    period_end: date | None
    period_start_matches_earliest_payment: bool
    latest_parseable_maturity_date: date | None
    maturity_date_after_period_start: bool | None  # None = cannot be determined from available text


def extract_interest_claim(
    claim_text: str, earliest_payment_date: date | None, contract_maturity_dates: list[str]
) -> InterestClaimResult | None:
    amount_match = _INTEREST_AMOUNT_BEFORE_LABEL.search(claim_text) or _INTEREST_AMOUNT_AFTER_LABEL.search(claim_text)
    period_match = _INTEREST_PERIOD_PATTERN.search(claim_text)
    if amount_match is None and period_match is None:
        return None

    claimed_amount = _normalize_amount(amount_match.group(1)) if amount_match else None
    period_start = _parse_numeric_date(period_match.group(1)) if period_match else None
    period_end = _parse_numeric_date(period_match.group(2)) if period_match else None

    period_start_matches_earliest_payment = (
        period_start is not None and earliest_payment_date is not None and period_start == earliest_payment_date
    )

    parseable_maturities = [d for raw in contract_maturity_dates if (d := _parse_numeric_date(raw)) is not None]
    latest_maturity = max(parseable_maturities) if parseable_maturities else None

    maturity_after_start: bool | None = None
    if latest_maturity is not None and period_start is not None:
        maturity_after_start = latest_maturity > period_start

    return InterestClaimResult(
        claimed_amount=claimed_amount,
        period_start=period_start,
        period_end=period_end,
        period_start_matches_earliest_payment=period_start_matches_earliest_payment,
        latest_parseable_maturity_date=latest_maturity,
        maturity_date_after_period_start=maturity_after_start,
    )
