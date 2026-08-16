"""Suffix -> DocumentExtractor lookup — the pipeline's only import from this
package besides the shared dataclasses/exceptions in `base.py`.
"""
from __future__ import annotations

from app.documents.extraction.base import DocumentExtractor
from app.documents.extraction.docx_extractor import DocxExtractor
from app.documents.extraction.pdf_extractor import PdfTextExtractor
from app.documents.extraction.txt_extractor import TxtExtractor
from app.documents.extraction.xlsx_extractor import XlsxExtractor

_EXTRACTORS: dict[str, DocumentExtractor] = {
    ".pdf": PdfTextExtractor(),
    ".docx": DocxExtractor(),
    ".txt": TxtExtractor(),
    ".csv": TxtExtractor(),
    ".xlsx": XlsxExtractor(),
}


def get_extractor(suffix: str) -> DocumentExtractor | None:
    """Returns None for a suffix with no working extractor (e.g. image
    formats — accepted as evidence uploads but not extractable text this
    phase) — the pipeline maps that to `DocumentStatus.UNSUPPORTED`, never
    a fabricated extraction.
    """
    return _EXTRACTORS.get(suffix)
