from __future__ import annotations

from app.domains.contracts.obligations import extract_obligations
from app.domains.contracts.structure_extractor import ContractStructureExtractor, classify_clause, normalize_text
from app.domains.contracts.summary import build_summary
from app.models.contracts import ClauseType

_SAMPLE_CONTRACT = """1. Предмет договора

1.1. Исполнитель обязуется оказать услуги, а Заказчик обязуется принять и оплатить услуги.

2. Цена и порядок оплаты

2.1. Стоимость услуг составляет 100 000 рублей.

2.2. Оплата производится Заказчиком в течение 10 рабочих дней с момента подписания акта.

3. Ответственность сторон

3.1. Сторона, нарушившая обязательства, несет ответственность в виде возмещения убытков в полном объеме.

4. Расторжение

4.1. Заказчик вправе отказаться от исполнения договора в любое время без объяснения причин.
"""


def test_extractor_segments_into_expected_number_of_clauses():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    # 4 headings + 4 numbered sub-clauses (+ possible trailing blank paragraph
    # depending on exact whitespace) — assert a tight range, not one brittle number.
    assert 8 <= len(clauses) <= 9


def test_extractor_preserves_original_text_verbatim():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    payment_clause = next(c for c in clauses if "10 рабочих дней" in c.original_text)
    assert "2.2." in payment_clause.original_text
    assert payment_clause.original_text.strip().startswith("2.2.")


def test_extractor_assigns_clause_numbers():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    numbered = [c for c in clauses if c.clause_number]
    assert "2.2" in [c.clause_number for c in numbered]


def test_extractor_classifies_payment_clause():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    payment_clause = next(c for c in clauses if "рабочих дней" in c.normalized_text)
    assert payment_clause.clause_type == ClauseType.PAYMENT


def test_extractor_classifies_liability_clause():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    liability_clause = next(c for c in clauses if "возмещения убытков" in c.normalized_text)
    assert liability_clause.clause_type == ClauseType.LIABILITY


def test_extractor_classifies_termination_clause():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    termination_clause = next(c for c in clauses if "отказаться от исполнения" in c.normalized_text)
    assert termination_clause.clause_type == ClauseType.TERMINATION


def test_classify_clause_unknown_text_returns_other_low_confidence():
    clause_type, confidence = classify_clause("совершенно нейтральный текст без ключевых слов")
    assert clause_type == ClauseType.OTHER
    assert confidence < 0.5


def test_normalize_text_collapses_whitespace():
    assert normalize_text("  hello \n  world  ") == "hello world"


def test_positions_are_within_bounds_and_non_overlapping_in_order():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    for c in clauses:
        assert 0 <= c.position_start < c.position_end <= len(_SAMPLE_CONTRACT)
    starts = [c.position_start for c in clauses]
    assert starts == sorted(starts)


def test_extract_obligations_finds_payment_deadline():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    obligations = extract_obligations(clauses)

    payment_obligations = [o for o in obligations if o.obligation_type == "payment" and o.deadline]
    assert len(payment_obligations) == 1
    assert "10" in payment_obligations[0].deadline
    assert payment_obligations[0].party == "Заказчик"


def test_build_summary_reflects_extracted_clauses():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    obligations = extract_obligations(clauses)

    summary = build_summary(clauses, [o.action for o in obligations])

    assert summary.subject is not None
    assert summary.liability is not None
    assert summary.termination is not None
    assert summary.payment_terms is not None
    assert len(summary.major_obligations) >= 1


def test_build_summary_missing_field_is_none_not_fabricated():
    extractor = ContractStructureExtractor()
    clauses = extractor.extract(_SAMPLE_CONTRACT)
    summary = build_summary(clauses, [])
    assert summary.confidentiality is None  # no confidentiality clause in the sample
    assert summary.ip is None
