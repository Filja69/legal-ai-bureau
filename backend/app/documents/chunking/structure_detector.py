"""Deterministic legal-document structure detection — Phase 9.2 brief §13.
No LLM: clause/article numbering in a real legal document is already
explicit in the text, so a regex is the honest tool here. When nothing
matches, the caller falls back to plain-text chunking (brief: "честный
fallback, не invented structure").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.documents.extraction.base import ExtractedDocument

# Matches, at the start of a line: "4.1", "4.1.2.", "Статья 309", "§ 12",
# "п. 5.2", "N 3" — the numbering conventions actually used in Russian legal
# documents (contracts, statutes, correspondence).
_CLAUSE_MARKER = re.compile(
    r"^(?P<num>"
    r"\d+(?:\.\d+){0,5}\.?"
    r"|Статья\s+\d+\.?"
    r"|Article\s+\d+\.?"
    r"|§\s?\d+\.?"
    r"|п\.\s?\d+(?:\.\d+)*\.?"
    r"|Раздел\s+[IVXLCDM\d]+\.?"
    r")\s+(?P<rest>\S.*)$",
    re.UNICODE,
)


@dataclass
class DetectedClause:
    clause_number: str | None
    text: str
    page_number: int | None
    section_path: str | None


class StructureDetector:
    def detect(self, extracted: ExtractedDocument) -> list[DetectedClause]:
        clauses: list[DetectedClause] = []
        for section in extracted.sections:
            clauses.extend(self._split_section(section.text, section.page_number, section.section_path))
        return clauses

    def _split_section(self, text: str, page_number: int | None, section_path: str | None) -> list[DetectedClause]:
        lines = text.split("\n")
        result: list[DetectedClause] = []
        current_number: str | None = None
        current_lines: list[str] = []

        def flush() -> None:
            body = "\n".join(current_lines).strip()
            if body:
                result.append(DetectedClause(current_number, body, page_number, section_path))

        for line in lines:
            match = _CLAUSE_MARKER.match(line.strip())
            if match:
                flush()
                current_number = match.group("num").rstrip(".")
                current_lines = [match.group("rest")]
            else:
                current_lines.append(line)
        flush()
        return result


def has_detected_structure(clauses: list[DetectedClause]) -> bool:
    return any(c.clause_number is not None for c in clauses)
