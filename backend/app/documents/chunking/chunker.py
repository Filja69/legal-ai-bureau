"""Chunk assembly — Phase 9.2 brief §14/§15. Consumes the structure
detector's output (or falls back to plain-text sliding-window chunking when
no structure was found) and produces provenance-carrying chunks ready to
persist as `DocumentChunk` rows. Offsets are computed against the exact
text this module joins together — the pipeline persists that same joined
text as `Document.extracted_text`, so offsets are always consistent with
what a lawyer sees when they open the document (brief §15 "юрист должен
иметь возможность пройти AI claim -> chunk -> page/section -> document").
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.documents.chunking.normalization import normalize_text
from app.documents.chunking.structure_detector import StructureDetector, has_detected_structure
from app.documents.extraction.base import ExtractedDocument

_MAX_CHUNK_CHARS = 2000
_FALLBACK_WINDOW_CHARS = 1500
_FALLBACK_OVERLAP_CHARS = 150


@dataclass
class Chunk:
    chunk_index: int
    page_number: int | None
    section_path: str | None
    text: str
    start_offset: int
    end_offset: int


@dataclass
class ChunkingResult:
    chunks: list[Chunk]
    normalized_text: str
    warnings: list[str]
    used_structure: bool


def _split_if_too_long(text: str) -> list[str]:
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]
    # Split on paragraph boundaries first, then hard-wrap any paragraph that's
    # still too long — never splits mid-word by accident more than necessary.
    pieces: list[str] = []
    buffer = ""
    for paragraph in text.split("\n"):
        candidate = f"{buffer}\n{paragraph}" if buffer else paragraph
        if len(candidate) > _MAX_CHUNK_CHARS and buffer:
            pieces.append(buffer)
            buffer = paragraph
        else:
            buffer = candidate
    if buffer:
        pieces.append(buffer)
    # Hard-wrap any single paragraph that alone exceeds the limit.
    final: list[str] = []
    for piece in pieces:
        while len(piece) > _MAX_CHUNK_CHARS:
            final.append(piece[:_MAX_CHUNK_CHARS])
            piece = piece[_MAX_CHUNK_CHARS:]
        if piece:
            final.append(piece)
    return final


def build_chunks(extracted: ExtractedDocument) -> ChunkingResult:
    warnings = list(extracted.warnings)
    clauses = StructureDetector().detect(extracted)
    structured = has_detected_structure(clauses)

    chunks: list[Chunk] = []
    text_parts: list[str] = []
    offset = 0
    idx = 0

    if structured:
        for clause in clauses:
            body = normalize_text(clause.text)
            if not body:
                continue
            label = clause.section_path
            if clause.clause_number:
                label = f"{label} п.{clause.clause_number}" if label else f"п.{clause.clause_number}"
            for piece in _split_if_too_long(body):
                start = offset
                end = start + len(piece)
                chunks.append(Chunk(idx, clause.page_number, label, piece, start, end))
                text_parts.append(piece)
                offset = end + 2  # matches the "\n\n" separator joined below
                idx += 1
    else:
        warnings.append("No deterministic clause/section structure detected — used plain-text fallback chunking.")
        # Slide the fallback window per SECTION (per PDF page, per DOCX
        # paragraph group), not across the whole flattened document — found
        # as a real gap this session (docs/PHASE-9-2-INTEGRATION-VERIFICATION.md):
        # windowing over `extracted.text` as one string silently dropped
        # page_number/section_path for every fallback chunk, which breaks
        # the citation-roundtrip guarantee (brief §15) for exactly the
        # documents that most need it (no detected structure = no other
        # provenance signal). A window can still span an entire section, but
        # never crosses a section boundary, so provenance is never lost.
        step = _FALLBACK_WINDOW_CHARS - _FALLBACK_OVERLAP_CHARS
        for section in extracted.sections:
            section_text = normalize_text(section.text)
            if not section_text:
                continue
            pos = 0
            while pos < len(section_text):
                piece = section_text[pos : pos + _FALLBACK_WINDOW_CHARS]
                if not piece:
                    break
                start = offset
                end = start + len(piece)
                chunks.append(Chunk(idx, section.page_number, section.section_path, piece, start, end))
                text_parts.append(piece)
                offset = end + 2
                idx += 1
                pos += step

    normalized_full_text = "\n\n".join(text_parts)
    return ChunkingResult(chunks=chunks, normalized_text=normalized_full_text, warnings=warnings, used_structure=structured)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
