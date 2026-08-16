"""Deterministic case-fact extraction — Phase 9.3 brief §7/§8/§9."""
from __future__ import annotations

import uuid

from app.domains.litigation.fact_extractor import extract_fact_candidates
from app.models.matters import Document, DocumentChunk, DocumentStatus, DocumentType, FactType


def _document(title: str = "Test Doc") -> Document:
    return Document(id=uuid.uuid4(), workspace_id=uuid.uuid4(), title=title, document_type=DocumentType.OTHER, status=DocumentStatus.READY)


def _chunk(document: Document, text: str, page: int | None = 1) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(), workspace_id=document.workspace_id, document_id=document.id, chunk_index=0,
        page_number=page, section_path=None, text=text, content_hash="x" * 64,
        embedding=[0.0], embedding_model="mock", embedding_namespace="mock:mock:1",
    )


def test_extracts_numeric_date_with_provenance():
    doc = _document()
    chunk = _chunk(doc, "Товар передан 14.03.2026 по акту приёма-передачи.", page=2)
    candidates = extract_fact_candidates(doc, chunk)
    date_candidates = [c for c in candidates if c.fact_type == FactType.DATE]
    assert len(date_candidates) == 1
    assert date_candidates[0].normalized_value == "2026-03-14"
    assert date_candidates[0].evidence.page_number == 2
    assert date_candidates[0].evidence.document_id == doc.id
    assert "14.03.2026" in date_candidates[0].evidence.excerpt


def test_extracts_wordy_date_and_normalizes_month():
    doc = _document()
    chunk = _chunk(doc, "Договор вступает в силу 5 марта 2026 г.")
    candidates = extract_fact_candidates(doc, chunk)
    date_candidates = [c for c in candidates if c.fact_type == FactType.DATE]
    assert any(c.normalized_value == "2026-03-05" for c in date_candidates)


def test_rejects_impossible_numeric_date():
    doc = _document()
    chunk = _chunk(doc, "Раздел 32.15.2026 не является датой.")
    candidates = extract_fact_candidates(doc, chunk)
    assert not [c for c in candidates if c.fact_type == FactType.DATE]


def test_extracts_amount_with_grouped_thousands():
    doc = _document()
    chunk = _chunk(doc, "Сумма к оплате составляет 150 000 руб.")
    candidates = extract_fact_candidates(doc, chunk)
    amount_candidates = [c for c in candidates if c.fact_type == FactType.AMOUNT]
    assert len(amount_candidates) == 1
    assert amount_candidates[0].normalized_value == "150000.00"


def test_extracts_amount_with_decimal():
    doc = _document()
    chunk = _chunk(doc, "Стоимость услуг: 99999,99 руб.")
    candidates = extract_fact_candidates(doc, chunk)
    amount_candidates = [c for c in candidates if c.fact_type == FactType.AMOUNT]
    assert amount_candidates[0].normalized_value == "99999.99"


def test_extracts_party_entity():
    doc = _document()
    chunk = _chunk(doc, 'Исполнитель — ООО "Ромашка", в лице генерального директора.')
    candidates = extract_fact_candidates(doc, chunk)
    party_candidates = [c for c in candidates if c.fact_type == FactType.PARTY]
    assert any(c.normalized_value == "Ромашка" for c in party_candidates)


def test_extracts_party_role():
    doc = _document()
    chunk = _chunk(doc, "Заказчик: ИП Иванов И.И.\nИсполнитель: ООО Ромашка")
    candidates = extract_fact_candidates(doc, chunk)
    party_candidates = [c for c in candidates if c.fact_type == FactType.PARTY]
    assert any(c.normalized_value.startswith("заказчик:") for c in party_candidates)
    assert any(c.normalized_value.startswith("исполнитель:") for c in party_candidates)


def test_no_facts_extracted_from_plain_text_without_structured_data():
    doc = _document()
    chunk = _chunk(doc, "Это обычный текст без дат, сумм или наименований сторон вообще.")
    candidates = extract_fact_candidates(doc, chunk)
    assert candidates == []


def test_excerpt_is_bounded_and_includes_match():
    doc = _document()
    long_prefix = "Предисловие. " * 30
    chunk = _chunk(doc, f"{long_prefix}Оплата 01.01.2026 произведена полностью.")
    candidates = extract_fact_candidates(doc, chunk)
    date_candidate = next(c for c in candidates if c.fact_type == FactType.DATE)
    assert "01.01.2026" in date_candidate.evidence.excerpt
    assert len(date_candidate.evidence.excerpt) < len(chunk.text)
