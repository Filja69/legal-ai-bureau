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
