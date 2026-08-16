"""Plain text extraction — TXT/CSV. Validation (app/documents/validation.py)
already confirmed the content decodes as UTF-8 before this runs.
"""
from __future__ import annotations

from app.documents.extraction.base import ExtractedDocument, ExtractedSection


class TxtExtractor:
    async def extract(self, content: bytes) -> ExtractedDocument:
        text = content.decode("utf-8-sig")
        return ExtractedDocument(
            text=text,
            sections=[ExtractedSection(text=text)],
            metadata={"char_count": len(text)},
            extractor="txt",
        )
