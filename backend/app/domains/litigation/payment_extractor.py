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
#
# The "по" -> "договор", "займа" -> "б/н"/"№", and "займа" -> "от" gaps all
# use \s* (zero-or-more) rather than \s+ — OCR'd scanned documents routinely
# drop the space at a narrow table-cell line wrap, producing "подоговору",
# "займаб/н", or (when no б/н or № is stated at all) "займаот" as one
# run-on word (all three found live on real OCR'd bank statements, e.g.
# "Перечисление средств подоговору процентного займаот 11.09.2024г."). \s*
# still requires the literal word ("по"/"займа") immediately adjacent, so
# this doesn't loosen what counts as a match, only where OCR lost a space.
_LOAN_PAYMENT_PURPOSE = re.compile(
    r"по\s*договор[а-яё]*\s+(?:процентного\s+)?займа"
    r"(?:\s*(?P<no_number>б/н)|\s*№\s*(?P<explicit_number>\S+))?"
    r"\s*от\s+(?P<date>\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    re.IGNORECASE,
)
_PAYMENT_PURPOSE_LINE = re.compile(r"Назначение\s+платежа\s*[:\-]?\s*(.+)", re.IGNORECASE)
# Trailing (?!\d) instead of \b: a \b boundary fails whenever the kopecks are
# immediately followed by a Cyrillic letter with no separator (e.g. a real
# extracted layout with no whitespace between the amount field and the next
# entity name, "2000000-00ООО ...") — Python's \w is Unicode-aware, so a
# digit directly abutting a Cyrillic letter is NOT a word boundary. The
# actual intent was just "kopecks are exactly two digits," which (?!\d)
# expresses without assuming anything about what character follows.
_AMOUNT_FIELD = re.compile(r"Сумма\s+(\d[\d\s]*)-(\d{2})(?!\d)")
# Fallback for the bank-statement (выписка по счету) layout — see the
# extract_payment_order_candidate() fallback branch's comment. Anchored
# on "a full date immediately followed by the amount" (the observed real
# row shape: "01 22.04.2025 5 000 000.00 044525593 ...") rather than a
# bare free-floating digit run — a plain \d[\d\s]*\.\d{2} scan is unsafe
# here because a thousands-grouping space can't be told apart from the
# single space that separates two genuinely different numbers on the
# same line (e.g. it would glom the date's own trailing digits into the
# amount: "...2025 5 000 000.00..." -> wrongly "20255000000.00").
_DECIMAL_AMOUNT_NEAR_DATE = re.compile(
    r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+(\d[\d \xa0 ]*)\.(\d{2})(?!\.\d)"
)
_DATE_NEAR_HEADER = re.compile(
    # The gap between the header/label and the date can itself contain
    # digits (a document number, e.g. "ПОРУЧЕНИЕ № 11 13.09.2024") — so this
    # is "any char, non-greedy" bridging, not \D-only, on the same line.
    # [ЁЕ] covers both the diaeresis and the (very common in real documents/
    # OCR output) plain-Е spelling of "ПЛАТЁЖНОЕ" — both are Cyrillic; a
    # Latin "E" here would never legitimately appear in Cyrillic text.
    r"(?:ПЛАТ[ЁЕ]ЖНОЕ\s+ПОРУЧЕНИЕ|Дата)[^\n]{0,20}?(\d{1,2}[./]\d{1,2}[./]\d{2,4})", re.IGNORECASE
)
# Legal-form prefix, either the standard abbreviation or its full official
# name — real payment-order text (depending on how the paying bank's system
# rendered that particular page) spells this out in full just as often as it
# abbreviates it ("ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ" alongside "ООО"
# for the exact same entity across different pages of the same document).
# These are standard, universally-defined Russian legal entity type names,
# not specific to any one company.
_LEGAL_FORM_PREFIX = (
    r"(?:ООО|ОАО|ПАО|ЗАО|АО|ИП"
    # \s* (not \s+) between ОГРАНИЧЕННОЙ and ОТВЕТСТВЕННОСТЬЮ — the same
# OCR space-drop class fixed elsewhere in this module; found live on a
# real bank statement ("ОГРАНИЧЕННОЙОТВЕТСТВЕННОСТЬЮ" as one run-on word).
r"|ОБЩЕСТВО\s+С\s+ОГРАНИЧЕННОЙ\s*ОТВЕТСТВЕННОСТЬЮ"
    r"|(?:ПУБЛИЧНОЕ|ЗАКРЫТОЕ|ОТКРЫТОЕ)\s+АКЦИОНЕРНОЕ\s+ОБЩЕСТВО"
    r"|АКЦИОНЕРНОЕ\s+ОБЩЕСТВО"
    r"|ИНДИВИДУАЛЬНЫЙ\s+ПРЕДПРИНИМАТЕЛЬ)"
)
# Optional short all-caps qualifier abbreviation (ГК, ТД, УК, ХК, etc.) between
# the legal-form prefix and the quoted name — common in real Russian company
# names ("ООО ГК «...»", "АО ТД «...»") and otherwise breaks the match entirely
# since the plain \s* gap can't span an extra word.
# Qualifier-to-quote gap is \s* (not \s+) for the same OCR reason as
# everywhere else in this module — real text seen with no space at all
# between the qualifier and the opening quote ('ГК"ЛЕДОВЫЙ...' as one run).
_ENTITY = re.compile(_LEGAL_FORM_PREFIX + r'\s*(?:[А-ЯЁ]{1,4}\s*)?[«"][^»"]+[»"]')
_LABEL_WINDOW = 150  # how far before a "Плательщик"/"Получатель" label an entity name is still considered "its" name — wide
# enough to bridge the extra boilerplate lines (form/field labels) real bank layouts commonly place between the two


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

    decimal_match = None
    amount_match = _AMOUNT_FIELD.search(text)
    if amount_match:
        amount = f"{amount_match.group(1).replace(' ', '')}.{amount_match.group(2)}"
    else:
        # Fallback for a different real document layout — a bank account
        # statement (выписка по счету) states the amount as a plain decimal
        # figure in a Дебет/Кредит column ("5 000 000.00"), not the
        # dash-kopeck format платёжное поручение uses ("5000000-00"). The
        # decimal point is the distinguishing signal versus a bare integer
        # like an account/BIK/INN number, which never carries one.
        decimal_match = _DECIMAL_AMOUNT_NEAR_DATE.search(text)
        if decimal_match:
            digits = decimal_match.group(2).replace(" ", "").replace(chr(0xA0), "").replace(chr(0x202F), "")
            amount = f"{digits}.{decimal_match.group(3)}"
            if payer is None and recipient is None:
                # A bank statement's transaction row names the counterparty
                # (never the account holder, who's named once in the document
                # header instead) immediately after the amount — e.g. "...5
                # 000 000.00 044525593 ИНН 7743188387Счет N ...ЛЕДОВЫЙ СЕРВИС".
                # Assigned to `payer`: every real example of this layout seen
                # so far is a recipient's own incoming-funds statement, i.e.
                # the counterparty is the payer. A statement showing outgoing
                # (Дебет) transactions would need real debit/credit-column
                # direction detection to assign this correctly — not built
                # here since no real evidence of that case has been seen yet;
                # deliberately left as a known scope limit rather than guessed.
                counterparty_window = text[decimal_match.end() : decimal_match.end() + 300]
                counterparty_match = _ENTITY.search(counterparty_window)
                if counterparty_match:
                    payer = counterparty_match.group(0)
        else:
            amount = None

    date_match = _DATE_NEAR_HEADER.search(text)
    if date_match:
        payment_date = _normalize_date(date_match.group(1))
    elif decimal_match is not None:
        # Bank-statement layout: no "ПЛАТЁЖНОЕ ПОРУЧЕНИЕ"/"Дата" header is
        # near enough to the transaction date for _DATE_NEAR_HEADER to find
        # it (the real column-header word "Дата" sits many lines above the
        # actual per-row date). The transaction date immediately preceding
        # the amount in the same row (already anchored by
        # _DECIMAL_AMOUNT_NEAR_DATE for the amount itself) is this layout's
        # own date field — reuse that match instead of leaving it unparsed.
        payment_date = _normalize_date(decimal_match.group(1))
    else:
        payment_date = None

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

    if payer is None and recipient is None and amount is None and payment_purpose is None and referenced_contract_date is None:
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
