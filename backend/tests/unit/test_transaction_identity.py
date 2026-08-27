"""Transaction identity — synthetic fixtures, deliberately different
amounts/dates/companies from any real case. Named scenarios A-I per the
product brief this module was built against.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.domains.litigation.transaction_identity import build_canonical_transactions, normalize_party_name
from app.models.matters import CasePaymentOrder

_CASE = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_DOC_PO = uuid.uuid4()
_DOC_STMT = uuid.uuid4()
_DOC_REGISTER = uuid.uuid4()
_TITLES = {_DOC_PO: "payment_order.pdf", _DOC_STMT: "bank_statement.pdf", _DOC_REGISTER: "register.pdf"}


def _order(
    *, amount: str | None, referenced_contract_date: date | None = None, referenced_contract_number: str | None = None,
    payment_date: date | None = None, payer: str | None = None, recipient: str | None = None,
    document_id: uuid.UUID = _DOC_PO, excerpt: str = "",
) -> CasePaymentOrder:
    return CasePaymentOrder(
        id=uuid.uuid4(), workspace_id=_WORKSPACE, case_id=_CASE, document_id=document_id,
        payment_date=payment_date, amount=amount, payer=payer, recipient=recipient,
        referenced_contract_date=referenced_contract_date, referenced_contract_number=referenced_contract_number,
        excerpt=excerpt,
    )


def test_a_exact_duplicate_two_identical_rows_merge():
    a = _order(amount="500000.00", payment_date=date(2025, 1, 5), payer="ООО Гамма", recipient="ООО Дельта")
    b = _order(amount="500000.00", payment_date=date(2025, 1, 5), payer="ООО Гамма", recipient="ООО Дельта", document_id=_DOC_STMT)
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 1
    assert len(result[0].evidence_sources) == 2
    assert not result[0].needs_review


def test_b_payment_order_plus_bank_statement_corroborate_via_payment_date():
    po = _order(
        amount="700000.00", payment_date=date(2025, 3, 10), payer="ООО Север", recipient="ООО Юг",
        document_id=_DOC_PO, excerpt="ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 5",
    )
    stmt = _order(
        amount="700000.00", payment_date=date(2025, 3, 10), document_id=_DOC_STMT,
        excerpt="Выписка по счету N 123",
    )
    result = build_canonical_transactions([po, stmt], _TITLES)
    assert len(result) == 1
    ct = result[0]
    assert len(ct.evidence_sources) == 2
    types = {e.evidence_type for e in ct.evidence_sources}
    assert types == {"payment_order", "bank_statement"}
    assert "payment_date" in ct.matched_signals


def test_c_register_plus_payment_order_corroborate_via_contract_number():
    po = _order(amount="900000.00", referenced_contract_number="42", document_id=_DOC_PO)
    register = _order(amount="900000.00", referenced_contract_number="42", document_id=_DOC_REGISTER)
    result = build_canonical_transactions([po, register], _TITLES)
    assert len(result) == 1
    assert "referenced_contract_number" in result[0].matched_signals


def test_d_same_amount_and_date_but_different_payment_numbers_still_merges():
    """A payment order's own document number and a bank statement's
    internal reference number commonly differ for the exact same real
    transaction — payment_date + amount agreeing is itself a strong
    enough signal regardless of the (deliberately not compared) numbers.
    """
    a = _order(amount="300000.00", payment_date=date(2025, 6, 1), referenced_contract_number="11")
    b = _order(amount="300000.00", payment_date=date(2025, 6, 1), referenced_contract_number="797", document_id=_DOC_STMT)
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 1


def test_e_same_amount_and_reference_but_different_dates_are_not_merged():
    a = _order(amount="400000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 2, 1))
    b = _order(amount="400000.00", referenced_contract_date=date(2025, 1, 1), payment_date=date(2025, 4, 1))
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 2


def test_f_two_different_payments_with_identical_amounts_are_not_merged():
    a = _order(amount="250000.00", payment_date=date(2025, 1, 1), payer="ООО Альфа")
    b = _order(amount="250000.00", payment_date=date(2025, 5, 1), payer="ООО Бета")
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 2


def test_g_ocr_formatting_differences_in_party_names_still_match():
    assert normalize_party_name('ООО ГК «Ледовый Сервис»') == normalize_party_name(
        "Общество с ограниченной ответственностью ГК ЛЕДОВЫЙ СЕРВИС"
    )
    # payer/recipient formatting noise is corroborating context on top of a
    # real merge signal (payment_date here) — never sufficient by itself,
    # see test_payer_recipient_match_alone_is_never_sufficient_to_merge.
    a = _order(amount="600000.00", payment_date=date(2025, 8, 1), payer='ООО ГК «Север»', recipient="ООО Юг")
    b = _order(
        amount="600000.00", payment_date=date(2025, 8, 1), payer="ОБЩЕСТВО С ОГРАНИЧЕННОЙОТВЕТСТВЕННОСТЬЮ ГК СЕВЕР",
        recipient="ООО Юг", document_id=_DOC_STMT,
    )
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 1
    assert "payer" in result[0].matched_signals
    assert "payment_date" in result[0].matched_signals


def test_payer_recipient_match_alone_is_never_sufficient_to_merge():
    """Real bug this caught: three genuinely different real payments
    (different dates) between the same two parties, for the same round
    amount, referencing the same loan agreement, were wrongly collapsed
    into one when payer/recipient counted as a sufficient merge signal.
    Recurring same-party, same-amount payments on different dates are an
    entirely ordinary real scenario (installments) — not a duplicate.
    """
    a = _order(
        amount="2000000.00", referenced_contract_date=date(2024, 9, 11), payment_date=date(2024, 9, 13),
        payer="ООО Ледовый Сервис", recipient="ООО Энерго",
    )
    b = _order(
        amount="2000000.00", referenced_contract_date=date(2024, 9, 11), payment_date=date(2024, 10, 1),
        payer="ООО Ледовый Сервис", recipient="ООО Энерго",
    )
    c = _order(
        amount="2000000.00", referenced_contract_date=date(2024, 9, 11), payment_date=date(2024, 10, 11),
        payer="ООО Ледовый Сервис", recipient="ООО Энерго",
    )
    result = build_canonical_transactions([a, b, c], _TITLES)
    assert len(result) == 3


def test_undated_row_does_not_transitively_bridge_two_distinct_dated_payments():
    """The transitivity trap: an undated corroborating row can't be safely
    assigned to one specific dated peer, so it must not act as a bridge
    that indirectly merges two otherwise-unmergeable dated transactions
    through union-find's transitive closure.
    """
    dated_1 = _order(
        amount="2000000.00", referenced_contract_date=date(2024, 9, 11), payment_date=date(2024, 9, 13),
        payer="ООО Ледовый Сервис",
    )
    dated_2 = _order(
        amount="2000000.00", referenced_contract_date=date(2024, 9, 11), payment_date=date(2024, 10, 1),
        payer="ООО Ледовый Сервис",
    )
    undated = _order(
        amount="2000000.00", referenced_contract_date=date(2024, 9, 11), payment_date=None,
        payer="ООО Ледовый Сервис", document_id=_DOC_STMT,
    )
    result = build_canonical_transactions([dated_1, dated_2, undated], _TITLES)
    dates = {ct.transaction_date for ct in result}
    assert date(2024, 9, 13) in dates
    assert date(2024, 10, 1) in dates
    assert dated_1.id != dated_2.id  # sanity: genuinely two different source rows stayed apart


def test_h_ambiguous_evidence_amount_and_reference_only_does_not_auto_merge():
    """Amount + referenced_contract_date alone must never be treated as
    sufficient — both rows are kept, each flagged needs_review, cross-
    referencing the other rather than being silently guessed together.
    """
    a = _order(amount="200000.00", referenced_contract_date=date(2025, 1, 1))
    b = _order(amount="200000.00", referenced_contract_date=date(2025, 1, 1), document_id=_DOC_STMT)
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 2
    assert all(ct.needs_review for ct in result)
    assert all(ct.review_reason is not None for ct in result)


def test_register_and_bank_statement_dates_one_day_apart_are_flagged_not_merged():
    """Real production bug: a consolidated payment register recorded a
    transfer as 06.05.2025 while the corroborating bank statement for the
    same real transfer recorded it as 07.05.2025 (instruction date vs.
    value/posting date — an ordinary banking artifact). Before this fix,
    _conflicts() hard-blocked ANY date difference, so this pair got neither
    merged NOR flagged for review — it silently double-counted the same
    transaction in Money Flow. It must now surface as needs_review, and
    still must NOT auto-merge (a 1-day gap is not proof of identity).
    """
    register_row = _order(
        amount="3000000.00", payment_date=date(2025, 5, 6), referenced_contract_date=date(2024, 9, 11), document_id=_DOC_REGISTER
    )
    bank_statement_row = _order(
        amount="3000000.00", payment_date=date(2025, 5, 7), referenced_contract_date=date(2024, 9, 11), document_id=_DOC_STMT
    )
    result = build_canonical_transactions([register_row, bank_statement_row], _TITLES)
    assert len(result) == 2
    assert all(ct.needs_review for ct in result)
    assert all("payment_date_close" in (ct.review_reason or "") for ct in result)


def test_dates_four_days_apart_remain_a_hard_conflict():
    """Outside the close-date window, the existing hard-conflict rule still
    applies — no signal, no review flag, no merge."""
    a = _order(amount="3000000.00", payment_date=date(2025, 5, 6), referenced_contract_date=date(2024, 9, 11))
    b = _order(amount="3000000.00", payment_date=date(2025, 5, 10), referenced_contract_date=date(2024, 9, 11), document_id=_DOC_STMT)
    result = build_canonical_transactions([a, b], _TITLES)
    assert len(result) == 2
    assert not any(ct.needs_review for ct in result)


def test_i_three_evidence_sources_merge_into_one_canonical_transaction():
    po = _order(amount="800000.00", payment_date=date(2025, 7, 1), payer="ООО Мир", document_id=_DOC_PO)
    stmt = _order(amount="800000.00", payment_date=date(2025, 7, 1), payer="ООО Мир", document_id=_DOC_STMT)
    register = _order(amount="800000.00", payment_date=date(2025, 7, 1), payer="ООО Мир", document_id=_DOC_REGISTER)
    result = build_canonical_transactions([po, stmt, register], _TITLES)
    assert len(result) == 1
    assert len(result[0].evidence_sources) == 3
    document_ids = {e.document_id for e in result[0].evidence_sources}
    assert document_ids == {_DOC_PO, _DOC_STMT, _DOC_REGISTER}


def test_rows_without_amount_are_never_merged_and_still_produce_a_transaction():
    a = _order(amount=None, referenced_contract_date=date(2025, 1, 1))
    result = build_canonical_transactions([a], _TITLES)
    assert len(result) == 1
    assert len(result[0].evidence_sources) == 1


def test_empty_input_returns_empty():
    assert build_canonical_transactions([], _TITLES) == []
