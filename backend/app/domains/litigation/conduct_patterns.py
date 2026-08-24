"""Conduct-of-the-parties pattern detection — generalized from Money Flow
alone (`MoneyFlowSummary`), never from case-specific text. A payment pattern
is reported by its objective, countable properties (count, date span,
distinct payer/recipient strings) — never as "this looks like a mistake" or
"this looks deliberate"; the finding states the pattern and lets the reader
weigh it, same discipline as the rest of this package.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Thresholds are deliberately conservative and case-agnostic: a pattern
# finding requires real multiplicity (not two payments a day apart) so it
# doesn't fire on an ordinary case with a couple of routine transfers.
_MIN_TRANSACTIONS_FOR_PATTERN = 3
_MIN_SPAN_DAYS_FOR_PATTERN = 60


@dataclass
class PaymentPatternResult:
    transaction_count: int
    span_days: int | None
    distinct_payers: int
    distinct_recipients: int
    is_significant: bool
    description: str


def detect_payment_pattern(
    payment_dates: list[date], payers: list[str | None], recipients: list[str | None]
) -> PaymentPatternResult:
    distinct_payers = len({p for p in payers if p})
    distinct_recipients = len({r for r in recipients if r})
    dated = [d for d in payment_dates if d is not None]
    span_days = (max(dated) - min(dated)).days if len(dated) >= 2 else None

    is_significant = (
        len(payment_dates) >= _MIN_TRANSACTIONS_FOR_PATTERN
        and span_days is not None
        and span_days >= _MIN_SPAN_DAYS_FOR_PATTERN
    )

    if not is_significant:
        description = "Payment pattern does not meet the count/time-span threshold for a pattern finding."
    else:
        bank_clause = (
            f", involving {distinct_payers} distinct payer identit{'y' if distinct_payers == 1 else 'ies'}"
            if distinct_payers > 1
            else ""
        )
        description = (
            f"{len(payment_dates)} separate transfers were made over a {span_days}-day period{bank_clause}. "
            "This pattern may be relevant to characterizing whether the transfers were a single, isolated "
            "event or a sustained course of conduct — it does not by itself establish either party's "
            "characterization of the underlying transaction."
        )

    return PaymentPatternResult(
        transaction_count=len(payment_dates), span_days=span_days, distinct_payers=distinct_payers,
        distinct_recipients=distinct_recipients, is_significant=is_significant, description=description,
    )
