"""Normalization + structure detection + chunking — Phase 9.2 brief §12/§13/§14/§15."""
from __future__ import annotations

from app.documents.chunking.chunker import build_chunks, content_hash
from app.documents.chunking.normalization import normalize_text
from app.documents.chunking.structure_detector import StructureDetector, has_detected_structure
from app.documents.extraction.base import ExtractedDocument, ExtractedSection


def test_normalize_preserves_numbered_clauses_as_separate_lines():
    text = "4.1 Первое условие\n4.2 Второе условие\n4.3 Третье условие"
    normalized = normalize_text(text)
    lines = normalized.split("\n")
    assert lines == ["4.1 Первое условие", "4.2 Второе условие", "4.3 Третье условие"]


def test_normalize_collapses_intra_line_whitespace_only():
    text = "Раздел    4   —   Ответственность"
    assert normalize_text(text) == "Раздел 4 — Ответственность"


def test_normalize_collapses_excess_blank_lines_but_keeps_paragraph_breaks():
    text = "Пункт 1\n\n\n\n\nПункт 2"
    normalized = normalize_text(text)
    assert normalized == "Пункт 1\n\nПункт 2"


def test_normalize_line_endings_and_unicode():
    text = "Строка 1\r\nСтрока 2\r"
    normalized = normalize_text(text)
    assert "\r" not in normalized


def test_structure_detector_finds_numbered_clauses():
    text = "1. Предмет договора\n\n1.1. Первое условие.\n1.2. Второе условие."
    doc = ExtractedDocument(text=text, sections=[ExtractedSection(text=text, page_number=1)])
    clauses = StructureDetector().detect(doc)
    assert has_detected_structure(clauses)
    numbers = [c.clause_number for c in clauses]
    assert "1" in numbers
    assert "1.1" in numbers
    assert "1.2" in numbers


def test_structure_detector_finds_statya_marker():
    text = "Статья 309 Общие положения об обязательствах"
    doc = ExtractedDocument(text=text, sections=[ExtractedSection(text=text)])
    clauses = StructureDetector().detect(doc)
    assert clauses[0].clause_number == "Статья 309"


def test_structure_detector_returns_no_structure_for_free_text():
    text = "Это обычный текст без какой-либо явной нумерации пунктов вообще."
    doc = ExtractedDocument(text=text, sections=[ExtractedSection(text=text)])
    clauses = StructureDetector().detect(doc)
    assert not has_detected_structure(clauses)


def test_chunker_uses_structured_chunks_when_available():
    text = "1. Предмет\n\n1.1. Первое условие.\n1.2. Второе условие."
    doc = ExtractedDocument(text=text, sections=[ExtractedSection(text=text, page_number=3)])
    result = build_chunks(doc)
    assert result.used_structure is True
    assert all("Fallback" not in w for w in result.warnings)
    assert any(c.page_number == 3 for c in result.chunks)
    assert any(c.section_path and "1.1" in c.section_path for c in result.chunks)


def test_chunker_falls_back_to_sliding_window_when_no_structure():
    text = "Обычный текст без нумерации. " * 200  # long, unstructured
    doc = ExtractedDocument(text=text, sections=[ExtractedSection(text=text)])
    result = build_chunks(doc)
    assert result.used_structure is False
    assert len(result.chunks) > 1
    assert any("fallback" in w.lower() for w in result.warnings)


def test_chunker_offsets_are_consistent_with_normalized_text():
    text = "1. Раздел\n\n1.1. Условие один.\n1.2. Условие два."
    doc = ExtractedDocument(text=text, sections=[ExtractedSection(text=text)])
    result = build_chunks(doc)
    for chunk in result.chunks:
        assert result.normalized_text[chunk.start_offset : chunk.end_offset] == chunk.text


def test_chunker_splits_overlong_clause():
    long_clause = "5. " + ("Очень длинное условие договора. " * 200)
    doc = ExtractedDocument(text=long_clause, sections=[ExtractedSection(text=long_clause)])
    result = build_chunks(doc)
    assert result.used_structure is True
    assert len(result.chunks) > 1


def test_content_hash_is_deterministic():
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("world")
