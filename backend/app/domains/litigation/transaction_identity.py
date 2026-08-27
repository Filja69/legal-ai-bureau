"""Transaction identity — read-time canonical-transaction assembly over
already-persisted `CasePaymentOrder` rows. Supersedes `payment_dedup.py`'s
simpler collapse-and-discard approach: every real transaction is
represented as ONE `CanonicalTransaction` carrying ALL of its evidence
sources — no corroborating document is ever discarded; every one stays
visible as provenance on the canonical transaction it supports.

Multi-signal matching, never single-signal, per the explicit rule this
module is built against: amount alone is never sufficient to merge two
rows, and neither is amount + referenced_contract_date alone (two
genuinely different payments can easily share both — e.g. two
installments under the same loan agreement). A merge requires amount to
match AND at least one STRONG corroborating signal: an equal payment_date,
an equal referenced_contract_number, or a normalized payer/recipient
match. When two rows share only amount + referenced_contract_date (a WEAK
signal on its own) with nothing else agreeing, they are NOT merged — both
stay as their own canonical transactions, each flagged `needs_review` with
an explanation of exactly what did (and didn't) match, rather than guessed
together.

Grouping uses union-find so 3+ corroborating documents for the same real
transaction (payment order + bank statement + register entry, say) merge
into one canonical transaction as long as each pairwise link clears the
strong-signal bar — not just pairwise comparison.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from app.models.matters import CasePaymentOrder

_LEGAL_FORM_STRIP = re.compile(
    r"\b(ООО|ОАО|ПАО|ЗАО|АО|ИП|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s*ОТВЕТСТВЕННОСТЬЮ)\b", re.IGNORECASE
)
_PUNCT_STRIP = re.compile(r'[«»"\'.,]')
_WS_COLLAPSE = re.compile(r"\s+")

# Best-effort classification of a corroborating document's own layout, from
# the stored excerpt text alone (no extra DB round trip) — purely
# informational (shown to the lawyer as provenance context), never used in
# the matching decision itself.
_PAYMENT_ORDER_MARKER = re.compile(r"ПЛАТ[ЁЕ]ЖНОЕ\s+ПОРУЧЕНИЕ", re.IGNORECASE)
_BANK_STATEMENT_MARKER = re.compile(r"Выписка\s+по\s+счету", re.IGNORECASE)


def normalize_party_name(raw: str | None) -> str | None:
    """Collapses legal-form/punctuation/whitespace/case variance so "ООО ГК
    «Ледовый Сервис»" and "Общество с ограниченной ответственностью ГК
    ЛЕДОВЫЙ СЕРВИС" compare equal — normalizes formatting noise already
    proven to vary across real document layouts in this package (see
    payment_extractor.py's OCR-robustness fixes), never invents an identity.
    """
    if not raw:
        return None
    cleaned = _LEGAL_FORM_STRIP.sub(" ", raw)
    cleaned = _PUNCT_STRIP.sub(" ", cleaned)
    cleaned = _WS_COLLAPSE.sub(" ", cleaned).strip().upper()
    return cleaned or None


def _classify_evidence_type(excerpt: str) -> str:
    if _PAYMENT_ORDER_MARKER.search(excerpt):
        return "payment_order"
    if _BANK_STATEMENT_MARKER.search(excerpt):
        return "bank_statement"
    return "other"


def _completeness(row: CasePaymentOrder) -> int:
    return sum(1 for v in (row.payment_date, row.payer, row.recipient) if v is not None)


def _agreement_signals(a: CasePaymentOrder, b: CasePaymentOrder) -> list[str]:
    """Every signal that agrees between two rows — reported for
    transparency (`CanonicalTransaction.matched_signals`,
    `review_reason`), but ONLY `payment_date` and `referenced_contract_number`
    ever justify a merge on their own (see `_conflicts` / the merge loop in
    `build_canonical_transactions`). `payer`/`recipient` matching alone (even
    together with `referenced_contract_date`) is deliberately NOT
    sufficient: the same two counterparties paying the same amount under
    the same loan reference on genuinely different dates is a completely
    ordinary real scenario (installment payments), not a duplicate — see
    the anti-overfitting regression test for the real bug this caught
    (three same-amount, same-reference, DIFFERENT-date real payments were
    wrongly collapsed into one when payer/recipient counted as sufficient).
    """
    signals: list[str] = []
    if a.payment_date is not None and a.payment_date == b.payment_date:
        signals.append("payment_date")
    elif (
        a.payment_date is not None
        and b.payment_date is not None
        and 0 < abs((a.payment_date - b.payment_date).days) <= _CLOSE_DATE_WINDOW_DAYS
    ):
        # A register's own recorded date and a bank statement's date for the
        # SAME real transfer routinely differ by a day or two (instruction
        # date vs. value/posting date, or a weekend clearing gap) — a real,
        # ordinary banking artifact, not a coincidence to ignore. This is
        # deliberately NOT in _SUFFICIENT_ALONE (never auto-merges on its
        # own), only ever surfaces as a needs_review flag.
        signals.append("payment_date_close")
    if a.referenced_contract_date is not None and a.referenced_contract_date == b.referenced_contract_date:
        signals.append("referenced_contract_date")
    if a.referenced_contract_number is not None and a.referenced_contract_number == b.referenced_contract_number:
        signals.append("referenced_contract_number")
    payer_a, payer_b = normalize_party_name(a.payer), normalize_party_name(b.payer)
    if payer_a is not None and payer_a == payer_b:
        signals.append("payer")
    recipient_a, recipient_b = normalize_party_name(a.recipient), normalize_party_name(b.recipient)
    if recipient_a is not None and recipient_a == recipient_b:
        signals.append("recipient")
    return signals


_SUFFICIENT_ALONE = frozenset({"payment_date", "referenced_contract_number"})
# How many calendar days apart two rows' payment dates may be while still
# being flagged (never auto-merged) as a possible instruction-date/value-
# date pair for the same real transfer — see _agreement_signals. Real
# production data showed a register entry and its corroborating bank
# statement one calendar day apart for the same transaction.
_CLOSE_DATE_WINDOW_DAYS = 3


def _conflicts(a: CasePaymentOrder, b: CasePaymentOrder) -> bool:
    """A hard exclusion, checked before any signal counting: two rows with
    different, both-known payment dates MORE than _CLOSE_DATE_WINDOW_DAYS
    apart are never the same transaction, no matter how many other fields
    happen to agree. Without this, union-find's transitivity could bridge
    two genuinely different dated payments together through a shared
    undated corroborating row (which itself can't tell which of several
    same-amount, same-reference payments it corroborates) — exactly the
    real bug this module's tests were written to catch. Dates within the
    window are not a conflict — they fall through to _agreement_signals'
    "payment_date_close" WEAK signal instead, so they get flagged for
    review rather than silently ignored or force-merged.
    """
    return (
        a.payment_date is not None
        and b.payment_date is not None
        and abs((a.payment_date - b.payment_date).days) > _CLOSE_DATE_WINDOW_DAYS
    )


@dataclass
class EvidenceSource:
    payment_order_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    excerpt: str
    evidence_type: str  # "payment_order" | "bank_statement" | "other"


@dataclass
class CanonicalTransaction:
    id: str
    amount: str | None
    transaction_date: date | None
    payer: str | None
    recipient: str | None
    payment_purpose: str | None
    referenced_contract_type: str | None
    referenced_contract_date: date | None
    referenced_contract_number: str | None
    representative_document_id: uuid.UUID
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str | None = None


class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        root_x, root_y = self.find(x), self.find(y)
        if root_x != root_y:
            self._parent[root_y] = root_x


def _evidence_source(row: CasePaymentOrder, document_titles: dict[uuid.UUID, str]) -> EvidenceSource:
    excerpt = row.excerpt or ""
    return EvidenceSource(
        payment_order_id=row.id, document_id=row.document_id,
        document_title=document_titles.get(row.document_id, "(deleted)"),
        page_number=row.page_number, excerpt=excerpt, evidence_type=_classify_evidence_type(excerpt),
    )


def build_canonical_transactions(
    payment_orders: list[CasePaymentOrder], document_titles: dict[uuid.UUID, str]
) -> list[CanonicalTransaction]:
    n = len(payment_orders)
    uf = _UnionFind(n)

    by_amount: dict[str, list[int]] = {}
    ungrouped_idx: list[int] = []
    for i, row in enumerate(payment_orders):
        if row.amount is None:
            ungrouped_idx.append(i)
            continue
        by_amount.setdefault(row.amount, []).append(i)

    # (index, index, weak-only-signals) — recorded only when the pair
    # shares SOME signal but not a strong one, so they can be cross-flagged
    # needs_review below if they end up in different canonical transactions.
    review_pairs: list[tuple[int, int, list[str]]] = []

    for indices in by_amount.values():
        for a_pos in range(len(indices)):
            for b_pos in range(a_pos + 1, len(indices)):
                i, j = indices[a_pos], indices[b_pos]
                if _conflicts(payment_orders[i], payment_orders[j]):
                    continue
                signals = _agreement_signals(payment_orders[i], payment_orders[j])
                if set(signals) & _SUFFICIENT_ALONE:
                    uf.union(i, j)
                elif signals:
                    review_pairs.append((i, j, signals))

    ungrouped_set = set(ungrouped_idx)
    components: dict[int, list[int]] = {}
    for i in range(n):
        if i in ungrouped_set:
            continue
        components.setdefault(uf.find(i), []).append(i)

    canonical: list[CanonicalTransaction] = []
    idx_to_canonical_id: dict[int, str] = {}

    for idxs in components.values():
        rows = [payment_orders[i] for i in idxs]
        best = max(rows, key=lambda r: (_completeness(r), str(r.id)))
        matched: set[str] = set()
        for a_pos in range(len(idxs)):
            for b_pos in range(a_pos + 1, len(idxs)):
                matched.update(_agreement_signals(payment_orders[idxs[a_pos]], payment_orders[idxs[b_pos]]))

        ct = CanonicalTransaction(
            id=str(best.id), amount=best.amount, transaction_date=best.payment_date,
            payer=best.payer, recipient=best.recipient, payment_purpose=best.payment_purpose,
            referenced_contract_type=best.referenced_contract_type,
            referenced_contract_date=best.referenced_contract_date,
            referenced_contract_number=best.referenced_contract_number,
            representative_document_id=best.document_id,
            evidence_sources=[_evidence_source(r, document_titles) for r in rows],
            matched_signals=sorted(matched),
        )
        canonical.append(ct)
        for i in idxs:
            idx_to_canonical_id[i] = ct.id

    for i in ungrouped_idx:
        r = payment_orders[i]
        canonical.append(
            CanonicalTransaction(
                id=str(r.id), amount=r.amount, transaction_date=r.payment_date, payer=r.payer, recipient=r.recipient,
                payment_purpose=r.payment_purpose, referenced_contract_type=r.referenced_contract_type,
                referenced_contract_date=r.referenced_contract_date,
                referenced_contract_number=r.referenced_contract_number,
                representative_document_id=r.document_id,
                evidence_sources=[_evidence_source(r, document_titles)],
            )
        )
        idx_to_canonical_id[i] = canonical[-1].id

    ct_by_id = {ct.id: ct for ct in canonical}
    for i, j, signals in review_pairs:
        ci, cj = idx_to_canonical_id[i], idx_to_canonical_id[j]
        if ci == cj:
            continue
        for this_id, other_id in ((ci, cj), (cj, ci)):
            ct = ct_by_id[this_id]
            ct.needs_review = True
            note = (
                f"Possible duplicate of transaction {other_id} — only "
                f"{', '.join(signals)} agree, not enough to safely merge automatically."
            )
            if ct.review_reason is None:
                ct.review_reason = note
            elif note not in ct.review_reason:
                ct.review_reason = f"{ct.review_reason} {note}"

    return canonical
