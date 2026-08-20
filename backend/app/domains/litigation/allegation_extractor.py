"""Deterministic case-allegation extraction (E1, litigation evidence-layer
brief). Same discipline as `fact_extractor.py`: pure functions, no LLM call,
no DB access — a candidate only exists because a literal regex matched
literal chunk text, so every persisted `CaseAllegation` traces to real
provenance the same way `CaseFact.SUPPORTED` does.

Deliberately narrow scope (brief: "Do NOT attempt open-ended LLM allegation
extraction yet") — five bounded `AllegationType` categories, each with one
explicit Russian pattern, grounded in this specific case's real pleading
language (не публикуется — the real documents were read to derive these
patterns, never imported):

  NO_CONTRACT                   "договор ... заключен не был" / "... не был заключен"
  NO_LEGAL_BASIS                "правовых оснований ... не имеется"
  UNJUST_ENRICHMENT             "неосновательное обогащение"
  PAYMENT_BY_MISTAKE            "перечисления ... совершены ошибочно"
  FUTURE_CONTRACT_NEGOTIATIONS  "переговоры о заключении договора"

Known limitation, same as every other regex layer in this project: Russian-
pattern-only, and only catches these five phrasings — a differently-worded
allegation of the same legal substance will simply not be found (silent
gap, not an error), exactly as documented for fact_extractor.py.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from app.models.matters import AllegationType, Document, DocumentChunk

_EXCERPT_RADIUS = 120  # wider than fact_extractor's 80 — allegation sentences run longer than a date/amount token

_PATTERNS: dict[AllegationType, re.Pattern[str]] = {
    AllegationType.NO_CONTRACT: re.compile(
        r"договор[а-яёА-ЯЁ\s]{0,60}?(?:не\s+был[а-я]?\s+заключ[её]н|заключ[её]н\s+не\s+был[а-я]?)", re.IGNORECASE
    ),
    AllegationType.NO_LEGAL_BASIS: re.compile(
        r"правовых\s+основани[а-яё]*\s+[а-яё\s]{0,40}?не\s+имеется", re.IGNORECASE
    ),
    AllegationType.UNJUST_ENRICHMENT: re.compile(r"неосновательн[а-яё]*\s+обогащени[а-яё]*", re.IGNORECASE),
    AllegationType.PAYMENT_BY_MISTAKE: re.compile(
        r"перечислени[а-яё]*\s+(?:были\s+)?совершен[а-яё]*\s+ошибочно", re.IGNORECASE
    ),
    AllegationType.FUTURE_CONTRACT_NEGOTIATIONS: re.compile(
        r"переговор[а-яё]*\s+о\s+заключении\s+договора(?:\s+займа)?", re.IGNORECASE
    ),
}

# Only these CaseDocumentRole values represent a party's own pleading text —
# extracting "NO_CONTRACT" out of, say, a payment order's boilerplate would
# misattribute an assertion to the wrong party.
ALLEGATION_ELIGIBLE_ROLES = {"claim", "response", "court_filing"}


@dataclass
class AllegationCandidate:
    document_id: uuid.UUID
    chunk_id: uuid.UUID | None
    page_number: int | None
    statement_text: str
    excerpt: str
    allegation_type: AllegationType


def _excerpt_around(text: str, start: int, end: int) -> str:
    lo = max(0, start - _EXCERPT_RADIUS)
    hi = min(len(text), end + _EXCERPT_RADIUS)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{text[lo:hi].strip()}{suffix}"


def _sentence_containing(text: str, start: int, end: int) -> str:
    """The whole sentence the match falls in, not just the matched phrase —
    `statement_text` should read as an actual assertion, e.g. "договор
    впоследствии не был заключен сторонами", not a bare regex fragment.
    """
    sentence_start = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    sentence_end_dot = text.find(".", end)
    sentence_end_nl = text.find("\n", end)
    candidates = [e for e in (sentence_end_dot, sentence_end_nl) if e != -1]
    sentence_end = min(candidates) + 1 if candidates else len(text)
    return text[sentence_start:sentence_end].strip()


def extract_allegation_candidates(document: Document, chunk: DocumentChunk) -> list[AllegationCandidate]:
    text = chunk.text
    candidates: list[AllegationCandidate] = []
    for allegation_type, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            candidates.append(
                AllegationCandidate(
                    document_id=document.id,
                    chunk_id=chunk.id,
                    page_number=chunk.page_number,
                    statement_text=_sentence_containing(text, m.start(), m.end()),
                    excerpt=_excerpt_around(text, m.start(), m.end()),
                    allegation_type=allegation_type,
                )
            )
    return candidates
