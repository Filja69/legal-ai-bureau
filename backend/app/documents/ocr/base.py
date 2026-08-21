"""OCR engine abstraction — same one-responsibility discipline as
`app/documents/extraction/base.py`'s `DocumentExtractor`: an `OcrEngine`
turns ONE rasterized page's bytes into text, nothing else. It never decides
whether a page NEEDS OCR (that's `PdfTextExtractor`'s job, per-page, against
the existing text-layer threshold) and never touches the database.

Self-hosted only (Tesseract) — deliberately not a cloud OCR API or an LLM
vision call, so no document content ever leaves the process. See
`tesseract_engine.py`'s module docstring for the full rationale.
"""
from __future__ import annotations

from typing import Protocol


class OcrEngineError(Exception):
    """OCR genuinely failed on a page (engine crashed, unreadable image,
    binary missing) — distinct from OCR simply producing little/no text for
    a blank or illegible page, which is not an error (see pdf_extractor.py).
    """


class OcrEngine(Protocol):
    async def ocr_image(self, image_bytes: bytes) -> str: ...
