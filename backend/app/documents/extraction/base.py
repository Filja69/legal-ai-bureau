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
    """Raised specifically when a PDF has no extractable text layer (a scan).
    Distinct from `ExtractionError` so the pipeline can map it to the honest
    `OCR_REQUIRED` status (brief §4) instead of `FAILED` — this is not a
    processing failure, it's an accurate statement that OCR (not implemented
    this phase) would be required to read this file.
    """

    def __init__(self, message: str = "This PDF has no extractable text layer (appears to be a scanned image).") -> None:
        super().__init__("OCR_REQUIRED", message)


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
