"""E3 — deterministic structured payment-order extraction. Synthetic
fixtures modeled on the generic Russian payment-order (платёжное поручение)
layout — generic company names, not any real client's documents.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.domains.litigation.payment_extractor import extract_payment_order_candidate
from app.models.matters import Document, DocumentChunk, DocumentType


def _document() -> Document:
    return Document(id=uuid.uuid4(), workspace_id=uuid.uuid4(), title="Платежное поручение", document_type=DocumentType.EVIDENCE)


def _chunk(text: str, page_number: int | None = 1) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), document_id=uuid.uuid4(), chunk_index=0,
        page_number=page_number, text=text, content_hash="x",
        embedding=[0.0] * 8, embedding_model="mock", embedding_namespace="mock:mock:8",
    )


_PAYMENT_WITH_BN = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 11 13.09.2024
Сумма 2000000-00
ООО "АЛЬФА ТРЕЙД"
Плательщик
ООО "БЕТА СЕРВИС"
Получатель
Назначение платежа Перечисление средств по договору процентного займа б/н от 11.09.2024г. НДС не облагается.
Исполнено 13.09.2024
"""

_PAYMENT_NO_BN = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ 797 01.10.2024
Сумма 2000000-00
ООО "АЛЬФА ТРЕЙД"
Плательщик
ООО "БЕТА СЕРВИС"
Получатель
Назначение платежа Перечисление средств по договору процентного займа от 11.09.2024г. НДС не облагается
ИСПОЛНЕНО
"""

_PAYMENT_UNRELATED_CONTRACT = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 5 05.05.2025
Сумма 500000-00
ООО "АЛЬФА ТРЕЙД"
Плательщик
ООО "БЕТА СЕРВИС"
Получатель
Назначение платежа Оплата по договору поставки №12 от 01.02.2025г.
Исполнено 05.05.2025
"""


def test_extracts_loan_payment_purpose_with_bn_variant():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_WITH_BN))
    assert candidate is not None
    assert candidate.referenced_contract_type == "договор процентного займа"
    assert candidate.referenced_contract_date == date(2024, 9, 11)
    assert candidate.referenced_contract_number is None  # "б/н" -- explicitly no number


def test_extracts_loan_payment_purpose_without_bn_variant():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_NO_BN))
    assert candidate is not None
    assert candidate.referenced_contract_type == "договор процентного займа"
    assert candidate.referenced_contract_date == date(2024, 9, 11)


def test_extracts_amount_payer_recipient():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_WITH_BN))
    assert candidate is not None
    assert candidate.amount == "2000000.00"
    assert candidate.payer is not None and "АЛЬФА ТРЕЙД" in candidate.payer
    assert candidate.recipient is not None and "БЕТА СЕРВИС" in candidate.recipient


def test_extracts_payment_date_and_execution_status():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_WITH_BN))
    assert candidate is not None
    assert candidate.payment_date == date(2024, 9, 13)
    assert candidate.execution_status == "executed"


def test_false_positive_regression_unrelated_contract_does_not_populate_loan_fields():
    """A payment referencing a SUPPLY contract must never populate
    referenced_contract_type/date — this is exactly what would let an
    unrelated payment masquerade as loan-agreement evidence.
    """
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_UNRELATED_CONTRACT))
    assert candidate is not None
    assert candidate.referenced_contract_type is None
    assert candidate.referenced_contract_date is None
    assert candidate.payment_purpose is not None and "поставки" in candidate.payment_purpose


def test_returns_none_for_chunk_with_nothing_recognizable():
    candidate = extract_payment_order_candidate(_document(), _chunk("Некоторый нерелевантный текст без полей платежа."))
    assert candidate is None


def test_provenance_fields_populated():
    document = _document()
    chunk = _chunk(_PAYMENT_WITH_BN, page_number=2)
    candidate = extract_payment_order_candidate(document, chunk)
    assert candidate is not None
    assert candidate.document_id == document.id
    assert candidate.chunk_id == chunk.id
    assert candidate.page_number == 2
    assert candidate.excerpt


# --- Real-world layout robustness regressions ---
# Fixtures below reproduce structural quirks observed in real extracted bank
# payment-order text (glued fields, spelling variants, qualifier abbreviations,
# wide label gaps) using entirely synthetic company names/amounts/dates —
# these are general layout-robustness fixes, not case-specific data.

_PAYMENT_AMOUNT_GLUED_TO_ENTITY = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 4 04.04.2025
Сумма 4000000-00ООО "ГАММА ТРЕЙД"
Счёт № 40702810300000001111Плательщик
Получатель ООО "ДЕЛЬТА СЕРВИС"
Назначение платежа Оплата по договору процентного займа б/н от 01.01.2025г.
"""

_PAYMENT_CYRILLIC_E_HEADER = """
ПЛАТЕЖНОЕ ПОРУЧЕНИЕ № 9 09.09.2025 Электронно
Сумма 900000-00
ООО "ГАММА ТРЕЙД"
Плательщик
ООО "ДЕЛЬТА СЕРВИС"
Получатель
Назначение платежа Оплата по договору процентного займа б/н от 01.01.2025г.
"""

_PAYMENT_QUALIFIER_ABBREVIATION_PAYER = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 2 02.02.2025
Сумма 200000-00
ООО ГК "СЕВЕРНЫЙ ПОЛЮС"
Плательщик
ООО "ДЕЛЬТА СЕРВИС"
Получатель
Назначение платежа Оплата по договору процентного займа б/н от 01.01.2025г.
"""

_PAYMENT_WIDE_LABEL_GAP_RECIPIENT = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 3 03.03.2025
Сумма 300000-00
ООО "ГАММА ТРЕЙД"
Плательщик
ИНН 1234567890 КПП 123456789
Счёт № 40702810300000002222ООО "ДЕЛЬТА СЕРВИС"
Вид оплаты Срок плат.
Наз. пл. Очер. плат.
Код Рез. поле  Получатель
Назначение платежа Оплата по договору процентного займа б/н от 01.01.2025г.
"""


def test_extracts_amount_when_glued_directly_to_next_entity_name():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_AMOUNT_GLUED_TO_ENTITY))
    assert candidate is not None
    assert candidate.amount == "4000000.00"


def test_extracts_date_header_with_plain_cyrillic_e_spelling():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_CYRILLIC_E_HEADER))
    assert candidate is not None
    assert candidate.payment_date == date(2025, 9, 9)


def test_extracts_payer_with_qualifier_abbreviation_before_quoted_name():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_QUALIFIER_ABBREVIATION_PAYER))
    assert candidate is not None
    assert candidate.payer is not None and "СЕВЕРНЫЙ ПОЛЮС" in candidate.payer


def test_extracts_recipient_across_wide_label_gap():
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_WIDE_LABEL_GAP_RECIPIENT))
    assert candidate is not None
    assert candidate.recipient is not None and "ДЕЛЬТА СЕРВИС" in candidate.recipient


_PAYMENT_SPELLED_OUT_LEGAL_FORM = """
ПЛАТЁЖНОЕ ПОРУЧЕНИЕ 500 05.05.2025
Сумма 500000-00
ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ ГК
"СЕВЕРНЫЙ ПОЛЮС"
Плательщик
ООО "ДЕЛЬТА СЕРВИС"
Получатель
Назначение платежа Оплата по договору процентного займа б/н от 01.01.2025г.
"""


def test_extracts_payer_spelled_out_in_full_legal_form_not_abbreviated():
    """Some payment-order pages spell out "Общество с ограниченной
    ответственностью" instead of abbreviating to "ООО" for the exact same
    entity — a rendering variant, not a different company.
    """
    candidate = extract_payment_order_candidate(_document(), _chunk(_PAYMENT_SPELLED_OUT_LEGAL_FORM))
    assert candidate is not None
    assert candidate.payer is not None and "СЕВЕРНЫЙ ПОЛЮС" in candidate.payer
