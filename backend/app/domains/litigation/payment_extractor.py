"""Deterministic structured payment-order extraction (E3, litigation
evidence-layer brief). Same pure-function, no-LLM, no-DB-access discipline
as `fact_extractor.py`/`allegation_extractor.py`.

Scope, stated plainly: this targets the standard Russian bank payment-order
(платёжное поручение) layout — a "Плательщик"/"Получатель" label on the line
after the paying/receiving entity's name, a "Сумма" field as digits-dash-
kopecks (e.g. "2000000-00"), and a "Назначение платежа" line. Real-world
scans/exports vary; a payment order whose OCR/extraction reorders these
labels away from their entity names will simply yield fewer structured
fields (silent gap, not a crash) — every field is Optional for exactly this
reason, and `excerpt`/`payment_purpose` always carry the raw text regardless
of whether the other fields parsed.

`referenced_contract_type/date/number` are deliberately anchored on
"договор(а) (процентного) займа" specifically, NOT any occurrence of the
generic word "договор" — a payment purpose reading e.g. "Оплата по договору
поставки №12" must never populate these fields, since that would let an
unrelated contract reference masquerade as loan-agreement evidence (see
contradiction_detector.py's false-positive test).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date

from app.models.matters import Document, DocumentChunk

_EXCERPT_RADIUS = 200

# "Перечисление средств по договору процентного займа б/н от 11.09.2024г." or
# "... договору процентного займа от 11.09.2024г." (no "б/н") or
# "... договору займа №5 от 11.09.2024г." (an explicit number) — one pattern,
# three optional/alternative number-designation branches.
_LOAN_PAYMENT_PURPOSE = re.compile(
    r"по\s+договор[а-яё]*\s+(?:процентного\s+)?займа"
    r"(?:\s+(?P<no_number>б/н)|\s+№\s*(?P<explicit_number>\S+))?"
    r"\s+от\s+(?P<date>\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    re.IGNORECASE,
)
_PAYMENT_PURPOSE_LINE = re.compile(r"Назначение\s+платежа\s*[:\-]?\s*(.+)", re.IGNORECASE)
_AMOUNT_FIELD = re.compile(r"Сумма\s+(\d[\d\s]*)-(\d{2})\b")
_DATE_NEAR_HEADER = re.compile(
    # The gap between the header/label and the date can itself contain
    # digits (a document number, e.g. "ПОРУЧЕНИЕ № 11 13.09.2024") — so this
    # is "any char, non-greedy" bridging, not \D-only, on the same line.
    r"(?:ПЛАТ[ЁE]ЖНОЕ\s+ПОРУЧЕНИЕ|Дата)[^\n]{0,20}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})", re.IGNORECASE
)
_ENTITY = re.compile(r'(?:ООО|АО|ПАО|ЗАО|ИП)\s*[«"][^»"]+[»"]')
_LABEL_WINDOW = 60  # how far after an entity name a "Плательщик"/"Получатель" label is still considered "its" label


@dataclass
class PaymentOrderCandidate:
    document_id: uuid.UUID
    chunk_id: uuid.UUID | None
    page_number: int | None
    excerpt: str
    payment_date: date | None = None
    amount: str | None = None
    payer: str | None = None
    recipient: str | None = None
    payment_purpose: str | None = None
    referenced_contract_type: str | None = None
    referenced_contract_date: date | None = None
    referenced_contract_number: str | None = None
    execution_status: str = "unknown"


def _normalize_date(raw: str) -> date | None:
    parts = re.split(r"[./]", raw)
    if len(parts) != 3:
        return None
    day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _find_party(text: str, label: str) -> str | None:
    """The entity-name match immediately (within _LABEL_WINDOW chars) BEFORE
    `label` — matches the observed real-world layout where the party's name
    appears, then the "Плательщик"/"Получатель" label on the next line.
    """
    for label_match in re.finditer(label, text):
        window_start = max(0, label_match.start() - _LABEL_WINDOW)
        window = text[window_start : label_match.start()]
        entity_matches = list(_ENTITY.finditer(window))
        if entity_matches:
            return entity_matches[-1].group(0)
    return None


def extract_payment_order_candidate(document: Document, chunk: DocumentChunk) -> PaymentOrderCandidate | None:
    """One payment order's worth of structured fields from one chunk's
    text — returns None only if NOTHING at all was recognized (not even an
    amount or a date), so an unrelated chunk doesn't produce an empty row.
    """
    text = chunk.text

    payer = _find_party(text, "Плательщик")
    recipient = _find_party(text, "Получатель")

    amount_match = _AMOUNT_FIELD.search(text)
    amount = f"{amount_match.group(1).replace(' ', '')}.{amount_match.group(2)}" if amount_match else None

    date_match = _DATE_NEAR_HEADER.search(text)
    payment_date = _normalize_date(date_match.group(1)) if date_match else None

    purpose_match = _PAYMENT_PURPOSE_LINE.search(text)
    payment_purpose = purpose_match.group(1).strip() if purpose_match else None

    referenced_contract_type: str | None = None
    referenced_contract_date: date | None = None
    referenced_contract_number: str | None = None
    loan_match = _LOAN_PAYMENT_PURPOSE.search(text)
    if loan_match:
        referenced_contract_type = "договор процентного займа"
        referenced_contract_date = _normalize_date(loan_match.group("date"))
        if loan_match.group("explicit_number"):
            referenced_contract_number = loan_match.group("explicit_number")
        # "б/н" or no designation at all both mean: no number was stated —
        # left None either way, distinguishable via payment_purpose's raw text.

    execution_status = "executed" if re.search(r"исполнен[оа]", text, re.IGNORECASE) else "unknown"

    if payer is None and recipient is None and amount is None and payment_purpose is None:
        return None

    return PaymentOrderCandidate(
        document_id=document.id,
        chunk_id=chunk.id,
        page_number=chunk.page_number,
        excerpt=text[:_EXCERPT_RADIUS].strip() + ("…" if len(text) > _EXCERPT_RADIUS else ""),
        payment_date=payment_date,
        amount=amount,
        payer=payer,
        recipient=recipient,
        payment_purpose=payment_purpose,
        referenced_contract_type=referenced_contract_type,
        referenced_contract_date=referenced_contract_date,
        referenced_contract_number=referenced_contract_number,
        execution_status=execution_status,
    )
