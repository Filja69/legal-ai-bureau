"""Self-hosted OCR via Tesseract — the only OCR backend this project uses.
Deliberately not a cloud OCR API (Google Vision/AWS Textract/Azure) or an
LLM vision call: both would send real (possibly confidential client)
document content to a third party, which requires separate authorization
this project doesn't have standing to assume. Tesseract runs entirely
inside the Railway container — nothing leaves the process.

Requires the `tesseract` binary (+ the Russian language pack) to be present
on PATH — installed via `nixpacks.toml`'s `aptPkgs` in production. Never
imported/instantiated eagerly at module load: `get_ocr_engine()` (registry.py)
probes for the binary at call time and returns `None` if it's missing, so a
dev/CI environment without Tesseract installed degrades to the pre-existing
`OCR_REQUIRED` behavior instead of crashing the app at import time.
"""
from __future__ import annotations

import asyncio
import shutil

import pytesseract
from PIL import Image, UnidentifiedImageError

from app.documents.ocr.base import OcrEngineError

_TESSERACT_BINARY_NAME = "tesseract"


def tesseract_available() -> bool:
    return shutil.which(_TESSERACT_BINARY_NAME) is not None


class TesseractOcrEngine:
    def __init__(self, language: str = "rus+eng") -> None:
        self._language = language

    async def ocr_image(self, image_bytes: bytes) -> str:
        """Runs the blocking Tesseract subprocess call in a worker thread —
        a single page at 200 DPI can take real wall-clock time (hundreds of
        ms to a few seconds), and this must not stall the event loop for
        every other concurrent request while it runs.
        """
        try:
            return await asyncio.to_thread(self._ocr_sync, image_bytes)
        except OcrEngineError:
            raise
        except Exception as exc:  # noqa: BLE001 — any Tesseract/PIL failure is an OCR failure, never a crash
            raise OcrEngineError(f"Tesseract OCR failed ({type(exc).__name__})") from exc

    def _ocr_sync(self, image_bytes: bytes) -> str:
        import io

        try:
            image = Image.open(io.BytesIO(image_bytes))
            image.load()
        except UnidentifiedImageError as exc:
            raise OcrEngineError("Rasterized page image could not be decoded") from exc
        return pytesseract.image_to_string(image, lang=self._language)
