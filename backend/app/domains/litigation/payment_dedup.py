"""Payment-order deduplication — read-time only, over already-persisted
`CasePaymentOrder` rows (never deletes or mutates them, matching this
package's "computed at read time" discipline used everywhere else for
cross-document synthesis, e.g. claim-vs-evidence contradictions).

Motivation: a real case commonly has more than one document describing the
SAME real transfer — e.g. the paying bank's payment order and the receiving
party's own bank statement for that exact transaction. Without
deduplication, Money Flow's total silently double-counts every corroborated
payment (found live: uploading three corroborating bank statements for
already-known payments inflated a real case's total from 14,000,000 to
21,000,000).

Two rows are treated as the same real transaction only when they agree on
BOTH `amount` and `referenced_contract_date` — the two fields
payment_extractor.py extracts most reliably across every document layout it
supports — AND their payment dates are consistent with describing one
event (at most one distinct non-null `payment_date` among them).

When a candidate group actually contains two or more DIFFERENT dated
transactions that happen to share the same amount and contract reference (a
real possibility — see the anti-overfitting test), a row with no date of
its own is NOT guessed into either one; it is left as its own separate
entry rather than silently (and possibly wrongly) merged.
"""
from __future__ import annotations

from app.models.matters import CasePaymentOrder


def _completeness(row: CasePaymentOrder) -> int:
    return sum(1 for v in (row.payment_date, row.payer, row.recipient) if v is not None)


def deduplicate_payment_orders(rows: list[CasePaymentOrder]) -> list[CasePaymentOrder]:
    groups: dict[tuple[str, object], list[CasePaymentOrder]] = {}
    ungrouped: list[CasePaymentOrder] = []
    for row in rows:
        if row.amount is None or row.referenced_contract_date is None:
            ungrouped.append(row)
            continue
        groups.setdefault((row.amount, row.referenced_contract_date), []).append(row)

    result = list(ungrouped)
    for group in groups.values():
        if len(group) == 1:
            result.append(group[0])
            continue
        distinct_dates = {r.payment_date for r in group if r.payment_date is not None}
        if len(distinct_dates) <= 1:
            # One real transaction, described by more than one document —
            # keep a single, most-complete representative, deterministically.
            best = max(group, key=lambda r: (_completeness(r), str(r.id)))
            result.append(best)
        else:
            # 2+ distinct real transactions share this amount+reference.
            # Every row is kept — an undated row here can't be safely
            # assigned to one specific dated transaction, so it's left
            # separate rather than guessed into one of them.
            result.extend(group)
    return result
