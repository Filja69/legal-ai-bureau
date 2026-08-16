"""PDF text extraction — text-layer PDFs only (Phase 9.2 brief §3/§4).

No OCR: a page with no extractable text is exactly what a scanned image
looks like to `pypdf`, and this phase deliberately does not send page
images to an LLM and call it "extraction" (brief §4 is explicit that this
would be fabrication). `OcrRequiredError` is raised instead, honestly.
"""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.documents.extraction.base import ExtractedDocument, ExtractedSection, ExtractionError, OcrRequiredError

# A page is treated as "has no text layer" if extraction yields fewer than
# this many non-whitespace characters — real text-layer pages from real
# legal documents are never this sparse; a few stray characters can come
# from a scanned page's embedded metadata/watermark without being real text.
_MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT = 20


class PdfTextExtractor:
    async def extract(self, content: bytes) -> ExtractedDocument:
        try:
            reader = PdfReader(BytesIO(content))
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

        sections: list[ExtractedSection] = []
        pages_with_text = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — a single malformed page must not abort the whole document
                page_text = ""
            if len(page_text.strip()) >= _MIN_CHARS_PER_PAGE_TO_COUNT_AS_TEXT:
                pages_with_text += 1
            sections.append(ExtractedSection(text=page_text, page_number=page_number))

        if pages_with_text == 0:
            raise OcrRequiredError()

        full_text = "\n\n".join(s.text for s in sections)
        warnings = []
        if pages_with_text < len(sections):
            warnings.append(f"{len(sections) - pages_with_text} of {len(sections)} pages had no extractable text layer")

        return ExtractedDocument(
            text=full_text,
            sections=sections,
            metadata={"page_count": len(sections), "pages_with_text": pages_with_text},
            extractor="pypdf",
            warnings=warnings,
        )
