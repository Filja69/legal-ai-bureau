"""Upload security validation — Phase 9.2 brief §5/§6/§30."""
from __future__ import annotations

import pytest

from app.documents.validation import DocumentValidationError, validate_upload
from tests.helpers.sample_files import (
    build_docx,
    build_docx_missing_manifest,
    build_minimal_pdf,
    build_xlsx,
    build_zip_bomb_docx,
)


def test_rejects_empty_file():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(b"", "contract.pdf")
    assert exc.value.code == "EMPTY_FILE"


def test_rejects_unsupported_extension():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(b"hello", "malware.exe")
    assert exc.value.code == "UNSUPPORTED_FORMAT"


def test_rejects_missing_extension():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(b"hello", "no_extension")
    assert exc.value.code == "UNSUPPORTED_FORMAT"


def test_accepts_real_pdf():
    result = validate_upload(build_minimal_pdf("hello"), "contract.pdf")
    assert result.detected_media_type == "application/pdf"
    assert result.suffix == ".pdf"


def test_rejects_fake_extension_pdf_content_is_actually_text():
    # extension/MIME mismatch (brief §5)
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(b"this is plain text, not a pdf", "contract.pdf")
    assert exc.value.code == "MIME_MISMATCH"


def test_rejects_fake_extension_txt_content_is_actually_pdf_bytes():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(build_minimal_pdf("hello"), "notes.txt")
    assert exc.value.code == "MIME_MISMATCH"


def test_accepts_real_docx():
    result = validate_upload(build_docx(["Раздел 1", "Текст пункта."]), "agreement.docx")
    assert result.detected_media_type.endswith("wordprocessingml.document")


def test_accepts_real_xlsx():
    result = validate_upload(build_xlsx([["a", "b"], ["1", "2"]]), "data.xlsx")
    assert result.detected_media_type.endswith("spreadsheetml.sheet")


def test_rejects_corrupted_docx_missing_office_manifest():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(build_docx_missing_manifest(), "agreement.docx")
    assert exc.value.code == "CORRUPTED_FILE"


def test_pdf_with_correct_magic_bytes_but_broken_internal_structure_passes_validation():
    # validate_upload only checks the magic-byte signature for PDF — deep
    # structural parsing is the extractor's job (test_document_extraction.py
    # covers the CORRUPTED_FILE outcome for this same input).
    result = validate_upload(b"%PDF-1.4\nnot really a valid pdf structure", "broken.pdf")
    assert result.detected_media_type == "application/pdf"


def test_rejects_zip_bomb_docx():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(build_zip_bomb_docx(), "bomb.docx")
    assert exc.value.code == "ZIP_BOMB_SUSPECTED"


def test_accepts_valid_utf8_txt():
    result = validate_upload("Привет, договор №1".encode(), "note.txt")
    assert result.detected_media_type == "text/plain"


def test_rejects_non_utf8_txt():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(b"\xff\xfe\x00\x01binary garbage", "note.txt")
    assert exc.value.code == "MIME_MISMATCH"


def test_rejects_fake_image_extension():
    with pytest.raises(DocumentValidationError) as exc:
        validate_upload(b"not a real png", "scan.png")
    assert exc.value.code == "MIME_MISMATCH"
