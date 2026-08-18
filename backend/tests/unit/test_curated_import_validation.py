"""Pure validation tests for CuratedImportInput — no DB required.

Covers rule 8 (curated-dataset task): HTTPS-only URLs, non-empty text, known
kind, consistent dates, explicit confirmed_official_source.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.domains.legal_knowledge.curated_import import (
    CuratedImportInput,
    CuratedImportKind,
    CuratedImportValidationError,
    validate_input,
)


def _law_article(**overrides) -> CuratedImportInput:
    defaults = dict(
        kind=CuratedImportKind.LAW_ARTICLE,
        source_url="https://pravo.gov.ru/some-doc",
        confirmed_official_source=True,
        title="Статья 333. Уменьшение неустойки",
        text="Если подлежащая уплате неустойка явно несоразмерна...",
        law_short_name="ГК РФ",
        article_number="333",
        valid_from=date(2015, 6, 1),
    )
    defaults.update(overrides)
    return CuratedImportInput(**defaults)


def _interpretation(**overrides) -> CuratedImportInput:
    defaults = dict(
        kind=CuratedImportKind.INTERPRETATION,
        source_url="https://vsrf.ru/documents/own/12345",
        confirmed_official_source=True,
        title="Постановление Пленума ВС РФ от 24.03.2016 N 7",
        text="В соответствии со статьей 333...",
        document_number="7",
        adoption_date=date(2016, 3, 24),
    )
    defaults.update(overrides)
    return CuratedImportInput(**defaults)


def test_valid_law_article_passes():
    validate_input(_law_article())


def test_valid_interpretation_passes():
    validate_input(_interpretation())


def test_rejects_non_https_source_url():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(source_url="http://pravo.gov.ru/some-doc"))
    assert any("HTTPS" in e for e in exc.value.errors)


def test_rejects_non_https_amending_act_url():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(amending_act_source_url="http://pravo.gov.ru/amending"))
    assert any("amending_act_source_url" in e and "HTTPS" in e for e in exc.value.errors)


def test_rejects_empty_text():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(text=""))
    assert any("text must not be empty" in e for e in exc.value.errors)


def test_rejects_whitespace_only_text():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(text="   \n  "))
    assert any("text must not be empty" in e for e in exc.value.errors)


def test_rejects_unknown_kind():
    bad_input = _law_article()
    bad_input.kind = "not_a_real_kind"  # type: ignore[assignment]
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(bad_input)
    assert any("Unknown document kind" in e for e in exc.value.errors)


def test_rejects_missing_confirmed_official_source():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(confirmed_official_source=None))
    assert any("confirmed_official_source" in e for e in exc.value.errors)


def test_accepts_explicit_false_confirmation():
    # False is a valid, explicit answer — only None (unset) is rejected.
    validate_input(_law_article(confirmed_official_source=False))


def test_rejects_effective_date_before_publication_date():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(publication_date=date(2015, 6, 1), effective_date=date(2015, 1, 1)))
    assert any("inconsistent dates" in e for e in exc.value.errors)


def test_rejects_law_article_missing_short_name():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(law_short_name=None))
    assert any("law_short_name" in e for e in exc.value.errors)


def test_rejects_law_article_missing_article_number():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(article_number=None))
    assert any("article_number" in e for e in exc.value.errors)


def test_rejects_law_article_missing_valid_from():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(valid_from=None))
    assert any("valid_from" in e for e in exc.value.errors)


def test_rejects_law_article_valid_to_before_valid_from():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(valid_from=date(2015, 6, 1), valid_to=date(2015, 1, 1)))
    assert any("valid_to" in e for e in exc.value.errors)


def test_rejects_interpretation_missing_document_number():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_interpretation(document_number=None))
    assert any("document_number" in e for e in exc.value.errors)


def test_rejects_interpretation_publication_before_adoption():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_interpretation(adoption_date=date(2016, 3, 24), publication_date=date(2016, 1, 1)))
    assert any("inconsistent dates" in e for e in exc.value.errors)


def test_accumulates_multiple_errors_at_once():
    with pytest.raises(CuratedImportValidationError) as exc:
        validate_input(_law_article(source_url="http://insecure", text="", law_short_name=None))
    assert len(exc.value.errors) >= 3
