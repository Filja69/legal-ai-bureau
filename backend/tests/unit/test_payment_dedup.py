"""Payment-order deduplication — synthetic fixtures, deliberately different
amounts/dates from any real case. Anti-overfitting focus: two genuinely
different transactions that happen to share the same amount and contract
reference must never be silently collapsed into one.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.domains.litigation.payment_dedup import deduplicate_payment_orders
from app.models.matters import CasePaymentOrder

_CASE = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_DOC_A = uuid.uuid4()
_DOC_B = uuid.uuid4()


def _order(
    *, amount: str | None, referenced_contract_date: date | None, payment_date: date | None = None,
    payer: str | None = None, recipient: str | None = None, document_id: uuid.UUID = _DOC_A,
) -> CasePaymentOrder:
    return CasePaymentOrder(
        id=uuid.uuid4(), workspace_id=_WORKSPACE, case_id=_CASE, document_id=document_id,
        payment_date=payment_date, amount=amount, payer=payer, recipient=recipient,
        referenced_contract_date=referenced_contract_date,
    )


def test_corroborating_undated_row_merges_into_its_dated_peer():
    """A bank-statement corroboration of a known payment order (same amount
    and reference, no payment_date of its own) must collapse into one entry.
    """
    dated = _order(
        amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 1, 5),
        payer="X", document_id=_DOC_A,
    )
    undated = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=None, document_id=_DOC_B)
    result = deduplicate_payment_orders([dated, undated])
    assert len(result) == 1
    assert result[0].payment_date == date(2025, 1, 5)  # the more complete row is kept
    assert result[0].payer == "X"


def test_two_different_transactions_sharing_amount_and_reference_are_not_merged():
    """Two REAL, distinct payments that happen to share the same amount and
    contract reference (a legitimate real-world pattern — e.g. two
    installments under the same loan agreement) must never be collapsed
    into one — this would silently understate the total.
    """
    first = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 2, 1))
    second = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 3, 1))
    result = deduplicate_payment_orders([first, second])
    assert len(result) == 2


def test_undated_row_not_guessed_into_either_of_two_distinct_dated_transactions():
    """When a group contains 2+ genuinely different dated transactions
    sharing the same amount+reference, an undated corroborating row can't
    be safely assigned to one of them — it must stay as its own entry
    rather than being silently merged into a possibly-wrong one.
    """
    first = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 2, 1))
    second = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 3, 1))
    undated = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1), payment_date=None)
    result = deduplicate_payment_orders([first, second, undated])
    assert len(result) == 3


def test_rows_without_amount_or_reference_are_never_merged():
    a = _order(amount=None, referenced_contract_date=date(2025, 1, 1))
    b = _order(amount="500000.00", referenced_contract_date=None)
    result = deduplicate_payment_orders([a, b])
    assert len(result) == 2


def test_different_amounts_are_never_merged():
    a = _order(amount="500000.00", referenced_contract_date=date(2025, 1, 1))
    b = _order(amount="600000.00", referenced_contract_date=date(2025, 1, 1))
    result = deduplicate_payment_orders([a, b])
    assert len(result) == 2


def test_empty_input_returns_empty():
    assert deduplicate_payment_orders([]) == []
