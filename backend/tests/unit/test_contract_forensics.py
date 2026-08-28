"""Contract Forensics — notarization detection, synthetic fixtures."""
from __future__ import annotations

import uuid

from app.domains.litigation.contract_forensics import extract_contract_terms

_DOC_ID = uuid.uuid4()


def test_notarized_agreement_is_detected():
    text = "Настоящий Договор займа удостоверен нотариусом города Москвы, зарегистрирован в реестре за номером 77/1-н."
    terms = extract_contract_terms(_DOC_ID, "notarized.pdf", text)
    assert terms.notarized is True


def test_boilerplate_mention_of_notary_is_not_treated_as_notarized():
    """A generic clause about providing documents 'to a notary if requested'
    is not evidence THIS instrument was itself notarized — must not false-
    positive on a bare mention of the word."""
    text = "Сторона обязуется предоставить контрагенту или нотариусу какие-либо документы по требованию."
    terms = extract_contract_terms(_DOC_ID, "unrelated.pdf", text)
    assert terms.notarized is False


def test_plain_unsigned_draft_is_not_notarized():
    text = "Проект договора займа (не подписан). Займодавец передает Заемщику 1 000 000 рублей."
    terms = extract_contract_terms(_DOC_ID, "draft.pdf", text)
    assert terms.notarized is False
