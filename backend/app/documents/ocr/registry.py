"""OCR engine factory — same settings-gated, lazy-import pattern as
`app/documents/storage/base.py`'s `get_document_storage()` and
`app/rag/embeddings/base.py`'s `get_embedding_provider()`.

Returns `None` (never raises) when OCR isn't usable — either explicitly
disabled (`OCR_ENABLED=false`) or the `tesseract` binary genuinely isn't on
PATH in this environment. `PdfTextExtractor` treats `None` exactly like it
already treats "OCR not implemented": pages with no text layer stay blank
and the document lands on the existing, honest `OCR_REQUIRED` status — this
is what keeps local dev/CI (no Tesseract installed) working unchanged.
"""
from __future__ import annotations

from app.config.settings import get_settings
from app.documents.ocr.base import OcrEngine


def get_ocr_engine() -> OcrEngine | None:
    settings = get_settings()
    if not settings.ocr_enabled:
        return None

    from app.documents.ocr.tesseract_engine import TesseractOcrEngine, tesseract_available

    if not tesseract_available():
        return None
    return TesseractOcrEngine(language=settings.ocr_language)
