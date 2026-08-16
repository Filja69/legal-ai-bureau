"""Text extraction — Phase 9.2 brief §3/§4/§10/§11."""
from __future__ import annotations

import pytest

from app.documents.extraction.base import ExtractionError, OcrRequiredError
from app.documents.extraction.docx_extractor import DocxExtractor
from app.documents.extraction.pdf_extractor import PdfTextExtractor
from app.documents.extraction.registry import get_extractor
from app.documents.extraction.txt_extractor import TxtExtractor
from app.documents.extraction.xlsx_extractor import XlsxExtractor
from tests.helpers.sample_files import build_blank_pdf, build_docx, build_docx_with_table, build_minimal_pdf, build_xlsx


@pytest.mark.asyncio
async def test_pdf_extracts_real_text_with_page_provenance():
    result = await PdfTextExtractor().extract(build_minimal_pdf("Supply Agreement", page_count=2))
    assert "Supply Agreement page 1" in result.text
    assert "Supply Agreement page 2" in result.text
    assert [s.page_number for s in result.sections] == [1, 2]
    assert result.extractor == "pypdf"


@pytest.mark.asyncio
async def test_pdf_with_no_text_layer_raises_ocr_required():
    with pytest.raises(OcrRequiredError):
        await PdfTextExtractor().extract(build_blank_pdf(page_count=1))


@pytest.mark.asyncio
async def test_corrupted_pdf_raises_extraction_error():
    with pytest.raises(ExtractionError) as exc:
        await PdfTextExtractor().extract(b"%PDF-1.4\nnot really a valid pdf structure")
    assert exc.value.code == "CORRUPTED_FILE"


@pytest.mark.asyncio
async def test_docx_extracts_paragraphs_and_heading_section_path():
    content = build_docx(["Раздел 1", "1.1. Первый пункт.", "1.2. Второй пункт."], headings={0: 1})
    result = await DocxExtractor().extract(content)
    assert any(s.section_path == "Раздел 1" and "Первый пункт" in s.text for s in result.sections)
    assert result.extractor == "python-docx"


@pytest.mark.asyncio
async def test_docx_extracts_tables():
    content = build_docx_with_table([["Сторона", "Роль"], ["ООО Ромашка", "Заказчик"]])
    result = await DocxExtractor().extract(content)
    assert len(result.tables) == 1
    assert result.tables[0].rows[1] == ["ООО Ромашка", "Заказчик"]
    assert "ООО Ромашка" in result.text


@pytest.mark.asyncio
async def test_corrupted_docx_raises_extraction_error():
    with pytest.raises(ExtractionError) as exc:
        await DocxExtractor().extract(b"not a docx at all")
    assert exc.value.code == "CORRUPTED_FILE"


@pytest.mark.asyncio
async def test_txt_extracts_utf8_text():
    result = await TxtExtractor().extract("Привет, договор №1".encode())
    assert result.text == "Привет, договор №1"
    assert result.extractor == "txt"


@pytest.mark.asyncio
async def test_xlsx_extracts_sheet_as_table():
    result = await XlsxExtractor().extract(build_xlsx([["Дата", "Сумма"], ["01.01.2026", "1000"]]))
    assert len(result.tables) == 1
    assert result.tables[0].rows[0] == ["Дата", "Сумма"]


def test_registry_returns_extractor_for_known_suffixes():
    assert isinstance(get_extractor(".pdf"), PdfTextExtractor)
    assert isinstance(get_extractor(".docx"), DocxExtractor)
    assert isinstance(get_extractor(".txt"), TxtExtractor)
    assert isinstance(get_extractor(".xlsx"), XlsxExtractor)


def test_registry_returns_none_for_unextractable_formats():
    assert get_extractor(".png") is None
    assert get_extractor(".jpg") is None
