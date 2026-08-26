"""Interest/damages timeline extraction — synthetic claim text, deliberately
different amounts/dates from any real case, and a deliberately different
word order for the "amount after label" variant so this doesn't overfit to
one real document's phrasing.
"""
from __future__ import annotations

from datetime import date

from app.domains.litigation.interest_damages import extract_interest_claim

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
