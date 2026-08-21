"""Text extraction abstraction — Phase 9.2 brief §10/§11.

One responsibility per extractor: FILE BYTES -> STRUCTURED TEXT. An
extractor must never call an LLM, never do legal reasoning, and never write
to the database — that's the pipeline's job (`app/domains/documents/
pipeline.py`), not this layer's.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ExtractionError(Exception):
    """A file could not be extracted at all (corrupted, unreadable) —
    machine-readable `code` + a message safe to show a user, same contract
    as `app.documents.validation.DocumentValidationError`.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class OcrRequiredError(ExtractionError):
    """Raised when a PDF has no extractable text layer AND OCR was never
    attempted on it — either OCR is disabled/unavailable in this
    environment (see `app/documents/ocr/registry.py`), or the document
    exceeds `Settings.ocr_max_pages_per_document`. Maps to `OCR_REQUIRED`
    (not `FAILED`): this states "OCR would help and wasn't run", not "OCR
    was run and it didn't work" — see `OcrFailedError` for that case.
    """

    def __init__(self, message: str = "This PDF has no extractable text layer (appears to be a scanned image).") -> None:
        super().__init__("OCR_REQUIRED", message)


class OcrFailedError(ExtractionError):
    """Raised when OCR WAS attempted (on at least one page) and the
    document still ends up with zero pages of usable text — either every
    OCR call errored (Tesseract crashed, corrupted rasterized image) or
    every attempt technically succeeded but produced illegible/empty
    output. Maps to `FAILED`, not `OCR_REQUIRED` — re-running OCR on the
    exact same file is not expected to fix this on its own.
    """

    def __init__(self, message: str = "OCR was attempted but produced no readable text.") -> None:
        super().__init__("OCR_FAILED", message)


@dataclass
class ExtractedTable:
    page_number: int | None
    rows: list[list[str]]


@dataclass
class ExtractedSection:
    """One page (PDF) or paragraph/heading (DOCX) — the smallest unit the
    extractor can attribute text to. `page_number` is populated for PDF,
    `section_path` for DOCX (e.g. "Раздел 4 > п.4.2"); an extractor
    populates whichever it can determine, never invents the other.
    """

    text: str
    page_number: int | None = None
    section_path: str | None = None
    is_heading: bool = False


@dataclass
class ExtractedDocument:
    text: str  # normalization-ready concatenation of all sections, in order
    sections: list[ExtractedSection] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # page_count, word_count, etc. — extractor-specific
    extractor: str = ""
    warnings: list[str] = field(default_factory=list)


class DocumentExtractor(Protocol):
    async def extract(self, content: bytes) -> ExtractedDocument: ...
