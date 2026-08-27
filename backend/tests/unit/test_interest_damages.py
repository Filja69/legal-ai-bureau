"""Interest/damages timeline extraction — synthetic claim text, deliberately
different amounts/dates from any real case, and a deliberately different
word order for the "amount after label" variant so this doesn't overfit to
one real document's phrasing.
"""
from __future__ import annotations

from datetime import date

from app.domains.litigation.interest_damages import extract_interest_calculation_table, extract_interest_claim

_CLAIM_AMOUNT_FIRST = (
    "Истец просит взыскать 777 000,50 руб. проценты за пользование чужими денежными средствами "
    "за период с 01.02.2025 по 15.08.2025."
)
_CLAIM_LABEL_FIRST = (
    "Требование о взыскании процентов за пользование чужими денежными средствами в размере 350000,00 руб. "
    "является обоснованным."
)
_CLAIM_NO_INTEREST_TEXT = "Истец просит взыскать основной долг в размере 1 000 000 руб."


def test_extracts_amount_first_variant_with_period():
    result = extract_interest_claim(_CLAIM_AMOUNT_FIRST, earliest_payment_date=None, contract_maturity_dates=[])
    assert result is not None
    assert result.claimed_amount == "777000.50"
    assert result.period_start == date(2025, 2, 1)
    assert result.period_end == date(2025, 8, 15)


def test_extracts_label_first_variant():
    result = extract_interest_claim(_CLAIM_LABEL_FIRST, earliest_payment_date=None, contract_maturity_dates=[])
    assert result is not None
    assert result.claimed_amount == "350000.00"


def test_returns_none_when_no_interest_text_present():
    result = extract_interest_claim(_CLAIM_NO_INTEREST_TEXT, earliest_payment_date=None, contract_maturity_dates=[])
    assert result is None


def test_flags_period_start_matching_earliest_payment():
    result = extract_interest_claim(
        _CLAIM_AMOUNT_FIRST, earliest_payment_date=date(2025, 2, 1), contract_maturity_dates=[]
    )
    assert result is not None
    assert result.period_start_matches_earliest_payment is True


def test_flags_maturity_date_after_period_start():
    result = extract_interest_claim(
        _CLAIM_AMOUNT_FIRST, earliest_payment_date=None, contract_maturity_dates=["01.01.2030"]
    )
    assert result is not None
    assert result.latest_parseable_maturity_date == date(2030, 1, 1)
    assert result.maturity_date_after_period_start is True


def test_wordy_unparseable_maturity_date_does_not_produce_a_false_comparison():
    """A fully-spelled-out wordy Russian maturity date (day and year in
    words too, not just the month) is genuinely beyond this module's
    parsing and must result in maturity_date_after_period_start=None
    (unknown), never a guessed True/False.
    """
    result = extract_interest_claim(
        _CLAIM_AMOUNT_FIRST, earliest_payment_date=None, contract_maturity_dates=["первого января две тысячи тридцатого года"]
    )
    assert result is not None
    assert result.latest_parseable_maturity_date is None
    assert result.maturity_date_after_period_start is None


def test_semi_wordy_maturity_date_is_parsed_numeric_day_and_year():
    """The common real-world contract format — numeric day, wordy month
    name, numeric year ("11 сентября 2027 г.") — must be parsed, not
    treated as unparseable; this is the exact format
    contract_forensics.py's DATE_WORDY pattern extracts maturity dates in.
    """
    result = extract_interest_claim(
        _CLAIM_AMOUNT_FIRST, earliest_payment_date=None, contract_maturity_dates=["11 сентября 2027 г."]
    )
    assert result is not None
    assert result.latest_parseable_maturity_date == date(2027, 9, 11)
    assert result.maturity_date_after_period_start is True


# --- Structured per-installment interest-table extraction ---
# Deliberately different amounts/dates/rates from the real case throughout.

_CLEAN_TABLE = (
    "Задолженность, руб. Период просрочки Дней Ставка Проценты, руб.\n"
    "500 000 01.02.2025 15.03.2025 42 | 16% | 365 9 205,48\n"
    "300 000 16.03.2025 30.04.2025 45 | 17% | 365 6 287,67\n"
    "Итого общий размер неустойки по состоянию на 30.04.2025 составляет: 15 493,15 руб.\n"
)


def test_extracts_clean_synthetic_table_with_all_rows_and_verifies_arithmetic():
    summary = extract_interest_calculation_table(_CLEAN_TABLE)
    assert summary.row_count == 2
    assert summary.unparsed_row_count == 0
    row1, row2 = summary.rows
    assert row1.principal_amount == "500000.00"
    assert row1.claimed_period_start == date(2025, 2, 1)
    assert row1.claimed_period_end == date(2025, 3, 15)
    assert row1.days == 42
    assert row1.rate_percent == "16"
    assert row1.claimed_interest_amount == "9205.48"
    assert row1.confidence == "high"
    assert row1.arithmetic_check == "matches_claimed"
    assert row2.principal_amount == "300000.00"
    assert summary.claimed_interest_total == "15493.15"
    assert summary.earliest_interest_start == date(2025, 2, 1)
    assert summary.latest_interest_end == date(2025, 4, 30)


def test_row_with_days_field_genuinely_missing_from_ocr_is_not_falsely_parsed():
    """Regression for a real corruption pattern: when OCR drops the days
    count entirely (date immediately followed by the rate%, no digits in
    between), the row must be reported unparsed rather than have the regex
    engine backtrack into the date itself to manufacture a bogus days count.
    """
    corrupted = "400 000 01.06.2025 31.12.2025 18% | 365 12 345,67\n"
    summary = extract_interest_calculation_table(corrupted)
    assert summary.row_count == 0
    assert summary.unparsed_row_count == 1


def test_truncated_principal_with_leading_zero_fragment_is_rejected_not_reported_as_zero():
    """Regression for a real corruption pattern: a line-wrap drops the
    leading digit(s) of the principal, leaving an OCR fragment like
    "000 000" immediately before the row. That fragment must never be
    reported as a confident principal of 0.00 — it must be treated as
    unavailable (None), keeping the row's confidence at "partial".
    """
    corrupted = "000 000 01.02.2025 15.03.2025 42 | 16% | 365 9 205,48\n"
    summary = extract_interest_calculation_table(corrupted)
    assert summary.row_count == 1
    row = summary.rows[0]
    assert row.principal_amount is None
    assert row.confidence == "partial"
    assert row.arithmetic_check == "cannot_verify"


def test_no_explicit_grand_total_sentence_leaves_claimed_interest_total_none():
    """Never silently substitute a Legal-AI-computed sum for the claimant's
    own stated total when the claimant's sentence isn't found in the text.
    """
    no_total = "500 000 01.02.2025 15.03.2025 42 | 16% | 365 9 205,48\n"
    summary = extract_interest_calculation_table(no_total)
    assert summary.claimed_interest_total is None
    assert any("No explicit claimant grand-total sentence" in w for w in summary.calculation_warnings)


def test_open_ended_period_is_flagged_with_its_own_start_date():
    text = (
        _CLEAN_TABLE
        + "Взыскать проценты за пользование чужими денежными средствами начиная с 01.05.2025 "
        "по дату фактического погашения задолженности."
    )
    summary = extract_interest_calculation_table(text)
    assert summary.interest_period_open_ended is True
    assert summary.open_ended_period_start == date(2025, 5, 1)


def test_unparsed_rows_are_counted_with_excerpts_for_transparency():
    mixed = _CLEAN_TABLE + "some garbled fragment 19% that never resolves into a full row\n"
    summary = extract_interest_calculation_table(mixed)
    assert summary.unparsed_row_count == 1
    assert "19%" in summary.unparsed_row_excerpts[0]


def test_empty_text_returns_empty_summary():
    summary = extract_interest_calculation_table("")
    assert summary.row_count == 0
    assert summary.unparsed_row_count == 0
    assert summary.claimed_interest_total is None
    assert summary.calculation_warnings == []
