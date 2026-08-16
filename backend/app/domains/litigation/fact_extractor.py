"""Deterministic case-fact extraction — Phase 9.3 brief §7/§8. Pure functions:
FILE CHUNKS -> candidate facts with real provenance. Never touches the
database (that's the API layer's job, same separation-of-concerns pattern as
`app/documents/extraction/`) and never calls an LLM — brief §7 is explicit
that "evidence support determines status," and the only evidence this module
produces is a literal regex match against literal chunk text, so every
candidate it emits is honestly `SUPPORTED` once persisted with its evidence
row. No narrative/free-text fact extraction (e.g. "goods were delivered on
time") is implemented this phase — only the atomic date/amount/party facts
the shared regex library extracts; see docs/PHASE-9-3-LITIGATION-RESULT.md
for the explicit scope note.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.domains.shared.legal_patterns import AMOUNT, DATE_NUMERIC, DATE_WORDY, PARTY_ENTITY, PARTY_ROLE
from app.models.matters import Document, DocumentChunk, FactType

_MONTHS_RU: dict[str, str] = {
    "январ": "01", "феврал": "02", "март": "03", "апрел": "04", "ма": "05",
    "июн": "06", "июл": "07", "август": "08", "сентябр": "09", "октябр": "10",
    "ноябр": "11", "декабр": "12",
}
_EXCERPT_RADIUS = 80


@dataclass
class FactEvidenceCandidate:
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID | None
    page_number: int | None
    section_path: str | None
    excerpt: str


@dataclass
class FactCandidate:
    fact_type: FactType
    statement: str
    normalized_value: str
    evidence: FactEvidenceCandidate


def _excerpt_around(text: str, start: int, end: int) -> str:
    lo = max(0, start - _EXCERPT_RADIUS)
    hi = min(len(text), end + _EXCERPT_RADIUS)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{text[lo:hi].strip()}{suffix}"


def _normalize_date_numeric(raw: str) -> str | None:
    parts = re.split(r"[./]", raw)
    if len(parts) != 3:
        return None
    day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        d, m, y = int(day), int(month), int(year)
    except ValueError:
        return None
    if not (1 <= d <= 31 and 1 <= m <= 12):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def _normalize_date_wordy(raw: str) -> str | None:
    match = re.match(r"(\d{1,2})\s+([а-яА-Я]+)\s+(\d{4})", raw)
    if not match:
        return None
    day, month_word, year = match.groups()
    month_word_lower = month_word.lower()
    month_num = next((num for stem, num in _MONTHS_RU.items() if month_word_lower.startswith(stem)), None)
    if month_num is None:
        return None
    return f"{int(year):04d}-{month_num}-{int(day):02d}"


def _normalize_amount(raw: str) -> str | None:
    # Strips every non-digit/non-separator character, including regular and
    # non-breaking (\xa0) thousands-grouping spaces.
    digits = re.sub(r"[^\d,.]", "", raw)
    digits = digits.replace(",", ".")
    if not digits:
        return None
    try:
        value = float(digits)
    except ValueError:
        return None
    return f"{value:.2f}"


def extract_fact_candidates(document: Document, chunk: DocumentChunk) -> list[FactCandidate]:
    """One document chunk in, its candidate facts out — the caller (case
    fact-extraction pipeline) is responsible for deduplicating candidates
    across chunks/documents into canonical `CaseFact` rows (brief §9, see
    `app/domains/litigation/fact_dedup.py`).
    """
    text = chunk.text
    candidates: list[FactCandidate] = []

    def evidence_for(start: int, end: int) -> FactEvidenceCandidate:
        return FactEvidenceCandidate(
            document_id=document.id,
            document_title=document.title,
            chunk_id=chunk.id,
            page_number=chunk.page_number,
            section_path=chunk.section_path,
            excerpt=_excerpt_around(text, start, end),
        )

    for m in DATE_NUMERIC.finditer(text):
        normalized = _normalize_date_numeric(m.group(0))
        if normalized:
            candidates.append(
                FactCandidate(FactType.DATE, f"Дата, упомянутая в документе: {m.group(0)}", normalized, evidence_for(m.start(), m.end()))
            )

    for m in DATE_WORDY.finditer(text):
        normalized = _normalize_date_wordy(m.group(0))
        if normalized:
            candidates.append(
                FactCandidate(FactType.DATE, f"Дата, упомянутая в документе: {m.group(0)}", normalized, evidence_for(m.start(), m.end()))
            )

    for m in AMOUNT.finditer(text):
        normalized = _normalize_amount(m.group(0))
        if normalized:
            candidates.append(
                FactCandidate(FactType.AMOUNT, f"Сумма, упомянутая в документе: {m.group(0)}", normalized, evidence_for(m.start(), m.end()))
            )

    for m in PARTY_ENTITY.finditer(text):
        name = m.group(1).strip()
        candidates.append(
            FactCandidate(FactType.PARTY, f"Юридическое лицо, упомянутое в документе: {m.group(0)}", name, evidence_for(m.start(), m.end()))
        )

    for m in PARTY_ROLE.finditer(text):
        role, name = m.group(1), m.group(2).strip()
        candidates.append(
            FactCandidate(FactType.PARTY, f"{role}: {name}", f"{role.lower()}:{name}", evidence_for(m.start(), m.end()))
        )

    return candidates
