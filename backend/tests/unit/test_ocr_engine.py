"""TesseractOcrEngine + registry — P0 scanned-PDF OCR support.

`test_tesseract_reads_synthetic_russian_image` is the one test in this
suite that exercises a REAL Tesseract binary (not a mock) — it's skipped
outright if `tesseract` isn't on PATH, and skipped again if no Cyrillic-
capable font can be found to render the synthetic test image, since neither
can be guaranteed in every environment this suite runs in (this sandbox has
neither installed). Every other test here (and in test_document_extraction.py)
injects a fake OcrEngine and never touches Tesseract at all — those are
what actually prove the pipeline wiring is correct.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.config.settings import get_settings
from app.documents.ocr.base import OcrEngineError
from app.documents.ocr.registry import get_ocr_engine
from app.documents.ocr.tesseract_engine import TesseractOcrEngine, tesseract_available

_CANDIDATE_CYRILLIC_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
]


def _find_cyrillic_font() -> str | None:
    for candidate in _CANDIDATE_CYRILLIC_FONTS:
        if Path(candidate).exists():
            return candidate
    return None


def _render_text_png(text: str, font_path: str) -> bytes:
    image = Image.new("RGB", (600, 150), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 50), text, fill="black", font=ImageFont.truetype(font_path, 32))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.skipif(not tesseract_available(), reason="tesseract binary not installed in this environment")
def test_tesseract_reads_synthetic_russian_image():
    font_path = _find_cyrillic_font()
    if font_path is None:
        pytest.skip("no Cyrillic-capable font found in this environment")

    import asyncio

    image_bytes = _render_text_png("Договор займа", font_path)
    result = asyncio.run(TesseractOcrEngine(language="rus").ocr_image(image_bytes))
    assert result.strip() != ""


@pytest.mark.asyncio
async def test_tesseract_engine_raises_ocr_engine_error_on_garbage_bytes():
    if not tesseract_available():
        pytest.skip("tesseract binary not installed in this environment")
    with pytest.raises(OcrEngineError):
        await TesseractOcrEngine().ocr_image(b"not an image at all")


def test_registry_returns_none_when_ocr_disabled(monkeypatch):
    settings = get_settings().model_copy(update={"ocr_enabled": False})
    import app.documents.ocr.registry as registry_module

    monkeypatch.setattr(registry_module, "get_settings", lambda: settings)
    assert get_ocr_engine() is None


def test_registry_returns_none_when_tesseract_binary_missing(monkeypatch):
    settings = get_settings().model_copy(update={"ocr_enabled": True})
    import app.documents.ocr.registry as registry_module
    import app.documents.ocr.tesseract_engine as tesseract_module

    monkeypatch.setattr(registry_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tesseract_module, "tesseract_available", lambda: False)
    assert get_ocr_engine() is None


def test_registry_returns_engine_when_enabled_and_binary_present(monkeypatch):
    settings = get_settings().model_copy(update={"ocr_enabled": True, "ocr_language": "rus+eng"})
    import app.documents.ocr.registry as registry_module
    import app.documents.ocr.tesseract_engine as tesseract_module

    monkeypatch.setattr(registry_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tesseract_module, "tesseract_available", lambda: True)
    engine = get_ocr_engine()
    assert isinstance(engine, TesseractOcrEngine)
