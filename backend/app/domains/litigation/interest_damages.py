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
# Contract maturity dates are stored as whatever raw text matched either
# legal_patterns.DATE_NUMERIC or DATE_WORDY (contract_forensics.py doesn't
# normalize them, since the two formats need different parsing). A maturity
# date is at least as likely to be wordy ("11 сентября 2027 г.") as numeric
# in real Russian contract drafting, so this module needs to parse both, not
# just silently treat every wordy maturity date as "unparseable."
_WORDY_MONTH = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
    "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
_WORDY_DATE = re.compile(
    r"\b(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s*г?\.?", re.IGNORECASE
)


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


def _parse_wordy_date(raw: str) -> date | None:
    match = _WORDY_DATE.search(raw)
    if not match:
        return None
    day, month_word, year = match.groups()
    month_word = month_word.lower()
    month = next((num for stem, num in _WORDY_MONTH.items() if month_word.startswith(stem)), None)
    if month is None:
        return None
    try:
        return date(int(year), month, int(day))
    except ValueError:
        return None


def parse_ru_date(raw: str) -> date | None:
    return _parse_numeric_date(raw) or _parse_wordy_date(raw)


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

    parseable_maturities = [d for raw in contract_maturity_dates if (d := parse_ru_date(raw)) is not None]
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


# --- Structured per-row interest/damages table extraction ---
#
# The single-sentence "за период с X по Y" extractor above covers claims
# that state one flat period. Real pleadings frequently instead compute
# interest per-installment (a table of principal / period / days / rate /
# amount rows, one block per underlying payment) because each payment
# accrues from its own date. This section extracts that row structure
# directly, tolerating the column layout coming apart under OCR (a real,
# repeatedly-observed failure mode for scanned Russian pleadings in this
# package — see payment_extractor.py's OCR-robustness fixes). A row that
# cannot be reassembled is reported as unparsed, never guessed at.
#
# The anchor for a row is the one fragment OCR rarely destroys: a
# start-date, end-date, days count, and percentage rate appearing in that
# order, immediately followed by a ruble amount. Everything else
# (principal, source payment date, legal basis) is opportunistic best-effort
# context gathered from nearby text, never required for a row to count.

_ROW_PATTERN = re.compile(
    # Both dates use a STRICT DD.MM.YYYY shape (not \d{1,2}/\d{2,4}) deliberately:
    # a flexible year width lets the regex engine backtrack and "steal" digits
    # from a genuinely complete date to satisfy a days-count field that OCR
    # actually dropped entirely, producing a corrupted date + bogus days count
    # instead of an honest non-match. A strict width cannot backtrack that way,
    # so a row whose days field is truly missing correctly fails to match here
    # and is counted as unparsed rather than silently misparsed.
    r"(\d{2}[./]\d{2}[./]\d{4})[^\d]{0,15}?(\d{2}[./]\d{2}[./]\d{4})[^\d]{0,15}?"
    r"(\d{1,3})[\s|]{1,6}(\d{1,2}(?:[.,]\d{1,2})?)\s*%\s*\|?\s*(365|366)?\s*\|?\s*(\d[\d \xa0]{0,14}[.,]\d{2})"
)
_STANDALONE_PERCENT = re.compile(r"\d{1,2}(?:[.,]\d{1,2})?\s*%")
# A genuine ruble principal is never legitimately written with a leading
# zero digit — "000 000" appearing before a row is an OCR truncation
# artifact (the true leading digit was dropped at a line-wrap), not a
# principal of zero. Requiring a nonzero leading digit rejects that
# artifact instead of confidently reporting a fabricated "0.00" principal.
_PRINCIPAL_LOOKBEHIND = re.compile(r"([1-9][\d \xa0]{2,14})\s*(?:руб[а-яё.]*)?\s*$")
_LEGAL_BASIS = re.compile(r"ст\.?\s*\d+[\d.]*\s*ГК\s*РФ", re.IGNORECASE)
_GRAND_TOTAL = re.compile(
    r"Итого[^\n]{0,80}?составляет:?\s*(\d[\d \xa0]{0,14}[.,]\d{2})\s*руб", re.IGNORECASE
)
_OPEN_ENDED_PERIOD = re.compile(
    r"начиная\s+с\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+по\s+дату\s+фактическ", re.IGNORECASE
)


@dataclass
class InterestCalculationRow:
    principal_amount: str | None
    source_payment_date: date | None
    claimed_period_start: date | None
    claimed_period_end: date | None
    days: int | None
    rate_percent: str | None
    claimed_interest_amount: str | None
    legal_reference_text: str | None
    excerpt: str
    confidence: str  # "high" (all fields present) | "partial" (core row only, principal/date missing)
    arithmetic_check: str | None  # "matches_claimed" | "does_not_match_claimed" | "cannot_verify" | None (no basis to check)


@dataclass
class InterestCalculationSummary:
    rows: list[InterestCalculationRow]
    claimed_principal_total: str | None
    claimed_interest_total: str | None  # CLAIMANT_CALCULATION — the grand total the claimant states, never LEGAL_AI's own conclusion
    interest_period_open_ended: bool  # claimant also demands interest continuing "по дату фактического погашения"
    open_ended_period_start: date | None
    earliest_interest_start: date | None
    latest_interest_end: date | None
    row_count: int
    unparsed_row_count: int
    unparsed_row_excerpts: list[str]
    calculation_warnings: list[str]


def _row_arithmetic_check(row_principal: str | None, rate: str | None, days: int | None, days_in_year: str, amount: str) -> str | None:
    if row_principal is None or rate is None or days is None:
        return "cannot_verify"
    try:
        principal_f = float(row_principal)
        rate_f = float(rate.replace(",", "."))
        amount_f = float(amount.replace(" ", "").replace("\xa0", "").replace(",", "."))
        year_days = int(days_in_year)
    except ValueError:
        return "cannot_verify"
    expected = principal_f * rate_f / 100 * days / year_days
    return "matches_claimed" if abs(expected - amount_f) < max(1.0, amount_f * 0.02) else "does_not_match_claimed"


def extract_interest_calculation_table(claim_text: str) -> InterestCalculationSummary:
    """Best-effort structured extraction of a per-installment interest/
    damages table from claim-document text. Designed to degrade honestly:
    a severely OCR-corrupted table yields fewer rows plus explicit
    `calculation_warnings`, never a fabricated complete table.
    """
    rows: list[InterestCalculationRow] = []
    matched_spans: list[tuple[int, int]] = []
    legal_basis_match = _LEGAL_BASIS.search(claim_text)
    legal_reference_text = legal_basis_match.group(0) if legal_basis_match else None

    for m in _ROW_PATTERN.finditer(claim_text):
        matched_spans.append(m.span())
        start_raw, end_raw, days_raw, rate_raw, year_raw, amount_raw = m.groups()
        period_start = parse_ru_date(start_raw)
        period_end = parse_ru_date(end_raw)
        days = int(days_raw)
        amount = _normalize_amount(amount_raw)
        year_days = year_raw or "365"

        lookbehind_window = claim_text[max(0, m.start() - 40) : m.start()]
        principal_match = _PRINCIPAL_LOOKBEHIND.search(lookbehind_window)
        principal_amount = _normalize_amount(principal_match.group(1)) if principal_match else None

        confidence = "high" if principal_amount is not None and period_start is not None and period_end is not None else "partial"
        arithmetic_check = (
            _row_arithmetic_check(principal_amount, rate_raw, days, year_days, amount_raw) if amount is not None else None
        )

        rows.append(
            InterestCalculationRow(
                principal_amount=principal_amount,
                source_payment_date=None,  # not reliably attributable per-row from claim-table text alone; see module docstring
                claimed_period_start=period_start,
                claimed_period_end=period_end,
                days=days,
                rate_percent=rate_raw.replace(",", "."),
                claimed_interest_amount=amount,
                legal_reference_text=legal_reference_text,
                excerpt=claim_text[max(0, m.start() - 20) : m.end() + 5].strip(),
                confidence=confidence,
                arithmetic_check=arithmetic_check,
            )
        )

    unparsed_row_excerpts: list[str] = []
    for pm in _STANDALONE_PERCENT.finditer(claim_text):
        if any(span[0] <= pm.start() < span[1] for span in matched_spans):
            continue
        unparsed_row_excerpts.append(claim_text[max(0, pm.start() - 40) : pm.end() + 10].strip().replace("\n", " "))

    warnings: list[str] = []
    if unparsed_row_excerpts:
        warnings.append(
            f"{len(unparsed_row_excerpts)} additional table row(s) contained a rate percentage but could not be "
            "reliably parsed into a complete row (likely OCR/formatting corruption) — see unparsed_row_excerpts."
        )
    if rows and any(r.principal_amount is None for r in rows):
        warnings.append(
            "Some parsed rows have no identifiable principal amount — the per-row principal could not be reliably "
            "matched from surrounding text, so per-row arithmetic cannot be verified for those rows."
        )

    grand_total_match = _GRAND_TOTAL.search(claim_text)
    claimed_interest_total = _normalize_amount(grand_total_match.group(1)) if grand_total_match else None
    if claimed_interest_total is None and rows:
        warnings.append(
            "No explicit claimant grand-total sentence was found; claimed_interest_total is not populated to avoid "
            "silently substituting a Legal-AI-computed sum for the claimant's own stated total."
        )

    principal_values = {r.principal_amount for r in rows if r.principal_amount is not None}
    claimed_principal_total = None
    if len(principal_values) == 1:
        claimed_principal_total = next(iter(principal_values))
    elif principal_values:
        try:
            claimed_principal_total = f"{sum(float(v) for v in principal_values):.2f}"
            warnings.append(
                "claimed_principal_total is a sum of distinct per-row principal amounts identified in the table; "
                "verify against the claim's own stated total, which this system did not find explicitly stated."
            )
        except ValueError:
            claimed_principal_total = None

    open_ended_match = _OPEN_ENDED_PERIOD.search(claim_text)
    interest_period_open_ended = open_ended_match is not None
    open_ended_period_start = parse_ru_date(open_ended_match.group(1)) if open_ended_match else None
    if interest_period_open_ended:
        warnings.append(
            "The claim also demands interest continuing beyond the stated total, from "
            f"{open_ended_period_start.isoformat() if open_ended_period_start else 'an unparsed date'} "
            "'until actual repayment' — this open-ended portion has no fixed claimed amount to extract."
        )

    starts = [r.claimed_period_start for r in rows if r.claimed_period_start is not None]
    ends = [r.claimed_period_end for r in rows if r.claimed_period_end is not None]

    return InterestCalculationSummary(
        rows=rows,
        claimed_principal_total=claimed_principal_total,
        claimed_interest_total=claimed_interest_total,
        interest_period_open_ended=interest_period_open_ended,
        open_ended_period_start=open_ended_period_start,
        earliest_interest_start=min(starts) if starts else None,
        latest_interest_end=max(ends) if ends else None,
        row_count=len(rows),
        unparsed_row_count=len(unparsed_row_excerpts),
        unparsed_row_excerpts=unparsed_row_excerpts,
        calculation_warnings=warnings,
    )
