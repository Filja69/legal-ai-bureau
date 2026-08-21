"""Text extraction — Phase 9.2 brief §3/§4/§10/§11, extended with OCR fallback."""
from __future__ import annotations

import pytest

import app.documents.extraction.pdf_extractor as pdf_extractor_module
from app.documents.extraction.base import ExtractionError, OcrFailedError, OcrRequiredError
from app.documents.extraction.docx_extractor import DocxExtractor
from app.documents.extraction.pdf_extractor import PdfTextExtractor
from app.documents.extraction.registry import get_extractor
from app.documents.extraction.txt_extractor import TxtExtractor
from app.documents.extraction.xlsx_extractor import XlsxExtractor
from app.documents.ocr.base import OcrEngineError
from tests.helpers.sample_files import build_blank_pdf, build_docx, build_docx_with_table, build_minimal_pdf, build_mixed_pdf, build_xlsx


@pytest.mark.asyncio
async def test_pdf_extracts_real_text_with_page_provenance():
    result = await PdfTextExtractor().extract(build_minimal_pdf("Supply Agreement", page_count=2))
    assert "Supply Agreement page 1" in result.text
    assert "Supply Agreement page 2" in result.text
    assert [s.page_number for s in result.sections] == [1, 2]
    assert result.extractor == "pypdf"


@pytest.mark.asyncio
async def test_pdf_with_no_text_layer_and_no_ocr_engine_raises_ocr_required(monkeypatch):
    # Explicit monkeypatch (not just relying on Tesseract being absent from
    # the test environment) — this must stay deterministic even in an
    # environment (e.g. Railway, where OCR support is actually installed)
    # that DOES have a real OCR engine available.
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: None)
    with pytest.raises(OcrRequiredError):
        await PdfTextExtractor().extract(build_blank_pdf(page_count=1))


@pytest.mark.asyncio
async def test_corrupted_pdf_raises_extraction_error():
    with pytest.raises(ExtractionError) as exc:
        await PdfTextExtractor().extract(b"%PDF-1.4\nnot really a valid pdf structure")
    assert exc.value.code == "CORRUPTED_FILE"


# --- OCR fallback (P0: scanned legal PDFs) ---
#
# All OCR-specific tests below inject a fake OcrEngine (matching the
# established monkeypatch-a-provider-factory convention already used for
# storage/embedding failures in tests/integration/test_documents_api.py) —
# never a real Tesseract call, so these pass regardless of whether the
# `tesseract` binary happens to be installed in whatever environment runs
# the suite. Only synthetic PDFs (tests/helpers/sample_files.py), never a
# real document, per this task's constraint.


class _FakeOcrEngine:
    """Returns a fixed string for every page (or a per-call sequence via
    `texts`), and can be told to fail — either always or only on the Nth call.
    """

    def __init__(self, texts: list[str] | None = None, *, fail_always: bool = False, fail_on_calls: set[int] | None = None):
        self._texts = texts
        self._fail_always = fail_always
        self._fail_on_calls = fail_on_calls or set()
        self.call_count = 0

    async def ocr_image(self, image_bytes: bytes) -> str:
        self.call_count += 1
        if self._fail_always or self.call_count in self._fail_on_calls:
            raise OcrEngineError("synthetic OCR failure")
        if self._texts is not None:
            return self._texts[self.call_count - 1]
        return "Договор займа от 11.09.2024"


@pytest.mark.asyncio
async def test_scanned_pdf_with_ocr_available_recovers_russian_text(monkeypatch):
    fake_engine = _FakeOcrEngine(texts=["Договор процентного займа между сторонами"])
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: fake_engine)

    result = await PdfTextExtractor().extract(build_blank_pdf(page_count=1))

    assert "Договор процентного займа между сторонами" in result.text
    assert result.sections[0].page_number == 1
    assert result.extractor == "pypdf+tesseract"
    assert result.metadata["pages_ocr_recovered"] == 1
    assert any("recovered via OCR" in w for w in result.warnings)
    assert fake_engine.call_count == 1


@pytest.mark.asyncio
async def test_mixed_document_only_ocrs_the_page_without_a_text_layer(monkeypatch):
    """Page 1 has a real pypdf-extractable text layer; page 2 does not.
    Only page 2 should ever reach the OCR engine, and the two pages' text
    must never be mixed together.
    """
    fake_engine = _FakeOcrEngine(texts=["Платёжное поручение №11 от 13.09.2024"])
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: fake_engine)

    content = build_mixed_pdf(["Supply Agreement Clause 1", None])
    result = await PdfTextExtractor().extract(content)

    assert fake_engine.call_count == 1  # only the blank page was OCR'd
    assert len(result.sections) == 2
    assert "Supply Agreement Clause 1" in result.sections[0].text
    assert "Платёжное поручение" not in result.sections[0].text  # no cross-page mixing
    assert result.sections[1].page_number == 2
    assert "Платёжное поручение №11 от 13.09.2024" in result.sections[1].text
    assert "Supply Agreement" not in result.sections[1].text  # no cross-page mixing
    assert result.metadata["pages_ocr_recovered"] == 1


@pytest.mark.asyncio
async def test_normal_text_pdf_never_invokes_ocr(monkeypatch):
    fake_engine = _FakeOcrEngine()
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: fake_engine)

    result = await PdfTextExtractor().extract(build_minimal_pdf("Supply Agreement", page_count=2))

    assert fake_engine.call_count == 0
    assert result.extractor == "pypdf"


@pytest.mark.asyncio
async def test_ocr_failure_on_every_page_raises_ocr_failed_not_ocr_required(monkeypatch):
    fake_engine = _FakeOcrEngine(fail_always=True)
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: fake_engine)

    with pytest.raises(OcrFailedError) as exc:
        await PdfTextExtractor().extract(build_blank_pdf(page_count=1))
    assert exc.value.code == "OCR_FAILED"
    assert fake_engine.call_count == 1


@pytest.mark.asyncio
async def test_partial_ocr_failure_leaves_document_readable_with_honest_warning(monkeypatch):
    """One of two scanned pages fails OCR; the other succeeds. The document
    must still process (not FAILED) since real text was recovered — the
    failure is honestly reflected in warnings, not silently dropped.
    """
    fake_engine = _FakeOcrEngine(texts=["Первая страница успешно распознана OCR"], fail_on_calls={2})
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: fake_engine)

    result = await PdfTextExtractor().extract(build_blank_pdf(page_count=2))

    assert result.metadata["pages_ocr_recovered"] == 1
    assert any("no readable text" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_ocr_skipped_when_page_count_exceeds_cap(monkeypatch):
    monkeypatch.setattr(pdf_extractor_module, "get_settings", lambda: _settings_with_ocr_cap(1))
    fake_engine = _FakeOcrEngine()
    monkeypatch.setattr(pdf_extractor_module, "get_ocr_engine", lambda: fake_engine)

    with pytest.raises(OcrRequiredError):
        await PdfTextExtractor().extract(build_blank_pdf(page_count=2))
    assert fake_engine.call_count == 0  # refused rather than attempting a partial OCR


def _settings_with_ocr_cap(max_pages: int):
    from app.config.settings import get_settings

    settings = get_settings()
    settings = settings.model_copy(update={"ocr_max_pages_per_document": max_pages})
    return settings


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
