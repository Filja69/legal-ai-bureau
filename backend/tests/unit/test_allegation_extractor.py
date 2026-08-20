"""E1 — deterministic case-allegation extraction. Synthetic fixtures only,
modeled on generic unjust-enrichment/loan-dispute pleading language, not any
real client's text.
"""
from __future__ import annotations

import uuid

from app.domains.litigation.allegation_extractor import extract_allegation_candidates
from app.models.matters import AllegationType, Document, DocumentChunk, DocumentType


def _document() -> Document:
    return Document(id=uuid.uuid4(), workspace_id=uuid.uuid4(), title="Исковое заявление", document_type=DocumentType.EVIDENCE)


def _chunk(text: str, page_number: int | None = 1) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), document_id=uuid.uuid4(), chunk_index=0,
        page_number=page_number, text=text, content_hash="x",
        embedding=[0.0] * 8, embedding_model="mock", embedding_namespace="mock:mock:8",
    )


def test_extracts_no_contract_allegation():
    text = "В устном порядке стороны вели переговоры. Впоследствии договор займа не был заключен сторонами."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    types = {c.allegation_type for c in candidates}
    assert AllegationType.NO_CONTRACT in types
    match = next(c for c in candidates if c.allegation_type == AllegationType.NO_CONTRACT)
    assert "не был заключен" in match.statement_text
    assert match.page_number == 1


def test_extracts_no_contract_allegation_alternate_word_order():
    text = "Договор займа заключен не был, что подтверждается перепиской сторон."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert any(c.allegation_type == AllegationType.NO_CONTRACT for c in candidates)


def test_extracts_no_legal_basis_allegation():
    text = "Поскольку правовых оснований для удержания денежных средств не имеется, они подлежат возврату."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert any(c.allegation_type == AllegationType.NO_LEGAL_BASIS for c in candidates)


def test_extracts_unjust_enrichment_allegation():
    text = "Полученные денежные средства являются неосновательным обогащением ответчика."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert any(c.allegation_type == AllegationType.UNJUST_ENRICHMENT for c in candidates)


def test_extracts_payment_by_mistake_allegation():
    text = "Истец был введен в заблуждение, и перечисления были совершены ошибочно."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert any(c.allegation_type == AllegationType.PAYMENT_BY_MISTAKE for c in candidates)


def test_extracts_future_contract_negotiations_allegation():
    text = "Между сторонами велись переговоры о заключении договора займа на определенных условиях."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert any(c.allegation_type == AllegationType.FUTURE_CONTRACT_NEGOTIATIONS for c in candidates)


def test_negative_fixture_generic_contract_performance_text_yields_no_allegations():
    """A document that just discusses ordinary contract performance — no
    allegation language at all — must produce zero candidates, not a
    false positive.
    """
    text = "Поставщик обязуется поставить товар в течение 30 дней с момента оплаты. Оплата производится в рублях."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert candidates == []


def test_negative_fixture_contract_was_concluded_does_not_match_no_contract():
    """The positive statement 'договор был заключен' must not be
    mis-detected as the NO_CONTRACT allegation.
    """
    text = "Договор поставки был заключен сторонами 01.01.2026 и исполнен в полном объеме."
    candidates = extract_allegation_candidates(_document(), _chunk(text))
    assert not any(c.allegation_type == AllegationType.NO_CONTRACT for c in candidates)


def test_every_candidate_carries_real_provenance():
    document = _document()
    chunk = _chunk("Денежные средства являются неосновательным обогащением.", page_number=3)
    candidates = extract_allegation_candidates(document, chunk)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.document_id == document.id
    assert candidate.chunk_id == chunk.id
    assert candidate.page_number == 3
    assert candidate.excerpt  # non-empty, bounded excerpt around the match
