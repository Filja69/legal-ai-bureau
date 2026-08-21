"""PDF text extraction — Phase 9.2 brief §3/§4, extended with OCR fallback.

Native text-layer extraction (pypdf) is tried first and always wins: OCR is
only ever invoked for a page whose native extraction yields fewer than
`_MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT` characters — a page with a real text
layer is never re-OCR'd (see get_extractor's registry — OCR is invisible to
callers when it isn't needed). This is a per-PAGE decision, never
per-document: a document with 8 native-text pages and 2 scanned pages keeps
its 8 native pages untouched and OCRs only the 2, so no text from different
pages is ever mixed into one section.

OCR itself is self-hosted (Tesseract, via `app.documents.ocr`) — see that
package's module docstring for why this is never a cloud OCR API or an LLM
vision call. `get_ocr_engine()` is resolved fresh on every call (not cached
at construction — this extractor instance is a long-lived module-level
singleton, see registry.py) so tests can monkeypatch it per-case and a
production environment's OCR availability is never stale.
"""
from __future__ import annotations

import asyncio
import io

import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config.settings import get_settings
from app.documents.extraction.base import ExtractedDocument, ExtractedSection, ExtractionError, OcrFailedError, OcrRequiredError
from app.documents.ocr.base import OcrEngineError
from app.documents.ocr.registry import get_ocr_engine

# A page is treated as "has no text layer" if extraction yields fewer than
# this many non-whitespace characters — real text-layer pages from real
# legal documents are never this sparse; a few stray characters can come
# from a scanned page's embedded metadata/watermark without being real text.
# Also the threshold OCR'd text must clear to count as "recovered" a page.
_MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT = 20


def _render_page_to_png(content: bytes, page_number: int, dpi: int) -> bytes:
    """1-indexed `page_number`, matching pypdf's enumeration used everywhere
    else in this module. PDFium's native unit is 1/72 inch, same as a PDF
    point, so `dpi / 72` is the correct render scale factor.
    """
    pdf = pdfium.PdfDocument(content)
    try:
        page = pdf[page_number - 1]
        bitmap = page.render(scale=dpi / 72)
        pil_image = bitmap.to_pil()
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        return buffer.getvalue()
    finally:
        pdf.close()


class PdfTextExtractor:
    async def extract(self, content: bytes) -> ExtractedDocument:
        try:
            reader = PdfReader(io.BytesIO(content))
        except PdfReadError as exc:
            raise ExtractionError("CORRUPTED_FILE", "PDF could not be parsed — the file may be corrupted") from exc

        if reader.is_encrypted:
            # pypdf can sometimes open an encrypted PDF with an empty password;
            # if it still reports encrypted after that attempt, refuse rather
            # than silently returning an empty/garbled extraction.
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 — any decrypt failure means we can't read it
                raise ExtractionError("CORRUPTED_FILE", "PDF is password-protected and could not be opened") from exc

        page_texts: list[str] = []
        pages_needing_ocr: list[int] = []  # 1-indexed
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — a single malformed page must not abort the whole document
                page_text = ""
            page_texts.append(page_text)
            if len(page_text.strip()) < _MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT:
                pages_needing_ocr.append(page_number)

        ocr_attempted = False
        pages_ocr_recovered = 0
        if pages_needing_ocr:
            settings = get_settings()
            ocr_engine = get_ocr_engine()
            if ocr_engine is not None and len(pages_needing_ocr) <= settings.ocr_max_pages_per_document:
                ocr_attempted = True
                for page_number in pages_needing_ocr:
                    try:
                        image_bytes = await asyncio.to_thread(_render_page_to_png, content, page_number, settings.ocr_dpi)
                        ocr_text = await ocr_engine.ocr_image(image_bytes)
                    except OcrEngineError:
                        ocr_text = ""  # this page's OCR failed — leave it blank, honestly reflected in warnings below
                    page_texts[page_number - 1] = ocr_text
                    if len(ocr_text.strip()) >= _MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT:
                        pages_ocr_recovered += 1
            # else: OCR unavailable/disabled, or this document exceeds the
            # page cap — deliberately do NOT attempt partial OCR in the
            # cap-exceeded case (a silently-incomplete result would be worse
            # than none); these pages simply stay blank, same as before OCR existed.

        sections = [ExtractedSection(text=text, page_number=n) for n, text in enumerate(page_texts, start=1)]
        pages_with_text = sum(1 for text in page_texts if len(text.strip()) >= _MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT)

        if pages_with_text == 0:
            if ocr_attempted:
                raise OcrFailedError(f"OCR was attempted on {len(pages_needing_ocr)} page(s) but produced no readable text.")
            raise OcrRequiredError()

        full_text = "\n\n".join(s.text for s in sections)
        warnings = []
        if pages_with_text < len(sections):
            warnings.append(f"{len(sections) - pages_with_text} of {len(sections)} pages had no extractable text layer")
        if pages_ocr_recovered:
            warnings.append(f"{pages_ocr_recovered} page(s) were recovered via OCR")
        if ocr_attempted and pages_ocr_recovered < len(pages_needing_ocr):
            warnings.append(f"OCR produced no readable text on {len(pages_needing_ocr) - pages_ocr_recovered} page(s)")

        return ExtractedDocument(
            text=full_text,
            sections=sections,
            metadata={"page_count": len(sections), "pages_with_text": pages_with_text, "pages_ocr_recovered": pages_ocr_recovered},
            extractor="pypdf+tesseract" if pages_ocr_recovered else "pypdf",
            warnings=warnings,
        )
