"""Manual human-curated legal document import — temporary operator/admin
workflow for staging (curated-dataset task, rule 10). NOT a public endpoint.

    python -m app.cli.curated_legal_import --input document.json --dry-run
    python -m app.cli.curated_legal_import --input document.json

    python -m app.cli.curated_legal_import --batch batch.jsonl --dry-run
    python -m app.cli.curated_legal_import --batch batch.jsonl

Never fetches anything itself (rule 11) — no automated download from
vsrf.ru/pravo.gov.ru or anywhere else. The operator personally reads the
official source page and supplies its exact text in the input file(s).
`--dry-run` (rule 9) runs every lookup/validation and prints exactly what
would be created/skipped/conflicted, without a single `session.add()` or
`session.commit()` — see CuratedImportService.preview()/preview_batch().

`--batch` is whole-file, all-or-nothing (starter-KB task): the entire JSONL
is dry-run-checked first, and if ANY line fails validation, conflicts with
an existing DB record, or collides with another line in the same file,
NOTHING is written for the whole batch — never a partial import.

Input JSON — one document per file (or one per line in a `--batch` JSONL
file), `kind` selects the shape:

    law_article:
        {
          "kind": "law_article",
          "source_url": "https://...",              (required, HTTPS)
          "confirmed_official_source": true,          (required, explicit)
          "title": "Статья 333. Уменьшение неустойки",
          "text": "...",                              (required, non-empty)
          "law_short_name": "ГК РФ",                   (required)
          "law_full_name": "Гражданский кодекс...",
          "code_type": "civil",
          "article_number": "333",                     (required)
          "clause_number": null,
          "jurisdiction": "RU",
          "publication_date": "1994-12-05",
          "effective_date": "2015-06-01",
          "valid_from": "2015-06-01",                  (required)
          "valid_to": null,
          "amending_act_title": "Федеральный закон от 08.03.2015 N 42-ФЗ",
          "amending_act_source_url": "https://...",
          "imported_by": "operator name/email"
        }

    interpretation (Постановление Пленума / обзор — no LawVersion is ever
    created for this kind, see curated_import.py's module docstring):
        {
          "kind": "interpretation",
          "source_url": "https://...",
          "confirmed_official_source": true,
          "title": "Постановление Пленума ВС РФ от 24.03.2016 N 7",
          "text": "...",
          "document_number": "7",                      (required)
          "document_subtype": "plenum_resolution",
          "jurisdiction": "RU",
          "adoption_date": "2016-03-24",
          "publication_date": "2016-03-24",
          "effective_date": "2016-03-24",
          "imported_by": "operator name/email"
        }
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from typing import Any

from app.db.session import get_session_factory
from app.domains.legal_knowledge.curated_import import (
    BatchLineOutcome,
    CuratedImportConflictError,
    CuratedImportInput,
    CuratedImportKind,
    CuratedImportResult,
    CuratedImportService,
    CuratedImportValidationError,
)
from app.rag.embeddings.base import get_embedding_provider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer

_DATE_FIELDS = ("publication_date", "effective_date", "valid_from", "valid_to", "adoption_date")


def _print(*lines: str) -> None:
    for line in lines:
        print(line)  # noqa: T201 — this is a CLI, stdout is the product


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_document_dict(raw: dict[str, Any]) -> CuratedImportInput:
    kind_str = raw.get("kind")
    try:
        kind = CuratedImportKind(kind_str)
    except ValueError:
        # Let validate_input() report this uniformly rather than crashing here —
        # construct with the raw string so CuratedImportValidationError fires.
        kind = kind_str  # type: ignore[assignment]

    for field_name in _DATE_FIELDS:
        if field_name in raw and raw[field_name] is not None:
            raw[field_name] = _parse_date(raw[field_name])

    return CuratedImportInput(
        kind=kind,
        source_url=raw.get("source_url", ""),
        confirmed_official_source=raw.get("confirmed_official_source"),
        title=raw.get("title", ""),
        text=raw.get("text", ""),
        jurisdiction=raw.get("jurisdiction", "RU"),
        publication_date=raw.get("publication_date"),
        effective_date=raw.get("effective_date"),
        imported_by=raw.get("imported_by"),
        law_short_name=raw.get("law_short_name"),
        law_full_name=raw.get("law_full_name"),
        code_type=raw.get("code_type"),
        article_number=raw.get("article_number"),
        clause_number=raw.get("clause_number"),
        valid_from=raw.get("valid_from"),
        valid_to=raw.get("valid_to"),
        amending_act_title=raw.get("amending_act_title"),
        amending_act_source_url=raw.get("amending_act_source_url"),
        document_number=raw.get("document_number"),
        document_subtype=raw.get("document_subtype"),
        adoption_date=raw.get("adoption_date"),
    )


def _load_input(path: str) -> CuratedImportInput:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return _parse_document_dict(raw)


def _load_batch(path: str) -> list[CuratedImportInput]:
    """One JSON object per non-blank line. A malformed line raises
    ValueError with its 1-based line number — caught by main() and reported
    the same way a validation failure is, before anything is touched.
    """
    inputs: list[CuratedImportInput] = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number}: invalid JSON — {exc}") from exc
            inputs.append(_parse_document_dict(raw))
    return inputs


def _print_result(result: CuratedImportResult) -> None:
    p = result.preview
    mode = "DRY RUN — nothing written" if result.dry_run else "IMPORTED"
    _print("=" * 70, f"{mode}", "=" * 70)
    _print(f"kind:               {p.kind}")
    _print(f"content_hash:       {p.content_hash}")
    _print(f"source:             {p.source_name}")
    _print(f"  {'would create new LegalSource row' if p.would_create_source else 'reuses existing LegalSource row'}")
    _print(f"  is_official to be set: {p.is_official_to_set}")
    if p.kind == "law_article":
        _print(f"law:                {p.law_short_name} ст.{p.article_number}")
        _print(f"  {'would create new Law row' if p.would_create_law else 'reuses existing Law row'}")
    else:
        _print(f"document_number:    {p.document_number}")

    if p.would_conflict:
        _print(
            "CONFLICT: an existing record with the same identity has a DIFFERENT content_hash "
            f"(source_document_id={p.conflicting_source_document_id}) — refusing to overwrite."
        )
    elif p.would_skip_duplicate:
        _print(f"DUPLICATE: identical content already imported (source_document_id={p.duplicate_of_source_document_id}) — no-op.")
    elif not result.dry_run:
        _print(f"source_document_id: {result.source_document_id}")
        if result.law_version_id:
            _print(f"law_version_id:     {result.law_version_id}")
        if result.legal_document_id:
            _print(f"legal_document_id:  {result.legal_document_id}")
        _print(f"embedding_indexed:  {result.embedding_indexed}")
    _print("=" * 70)


def _print_batch_outcomes(outcomes: list[BatchLineOutcome], *, dry_run: bool) -> None:
    all_ok = all(o.ok for o in outcomes)
    mode = "DRY RUN" if dry_run else ("IMPORTED" if all_ok else "REJECTED — nothing written")
    _print("=" * 70, f"BATCH ({len(outcomes)} lines) — {mode}", "=" * 70)
    for outcome in outcomes:
        if outcome.ok:
            p = outcome.result.preview if outcome.result else None
            label = f"{p.law_short_name} ст.{p.article_number}" if p and p.kind == "law_article" else (p.document_number if p else "")
            status = "duplicate (no-op)" if (p and p.would_skip_duplicate and not dry_run) else "ok"
            _print(f"  line {outcome.line_number}: OK  {label}  [{status}]")
        else:
            _print(f"  line {outcome.line_number}: FAIL  {outcome.error}")
    _print("=" * 70)
    if not all_ok:
        _print("At least one line failed — the ENTIRE batch was rejected. Fix the lines above and re-run.")


async def _run_single(session_factory, *, input_path: str, dry_run: bool) -> int:
    try:
        parsed_input = _load_input(input_path)
    except (OSError, json.JSONDecodeError) as exc:
        _print(f"Could not read/parse {input_path}: {exc}")
        return 1

    async with session_factory() as session:
        indexer = LegalChunkIndexer(session, get_embedding_provider())
        service = CuratedImportService(session, indexer=indexer)

        try:
            result = await service.preview(parsed_input) if dry_run else await service.import_document(parsed_input)
        except CuratedImportValidationError as exc:
            _print("VALIDATION FAILED — nothing written:")
            for error in exc.errors:
                _print(f"  - {error}")
            return 1
        except CuratedImportConflictError as exc:
            _print(f"CONFLICT — nothing written: {exc}")
            return 1

        _print_result(result)

        if not dry_run and not result.skipped:
            await session.commit()
        return 0


async def _run_batch(session_factory, *, batch_path: str, dry_run: bool) -> int:
    try:
        parsed_inputs = _load_batch(batch_path)
    except (OSError, ValueError) as exc:
        _print(f"Could not read/parse {batch_path}: {exc}")
        return 1

    if not parsed_inputs:
        _print(f"{batch_path} contains no document lines — nothing to do.")
        return 1

    async with session_factory() as session:
        indexer = LegalChunkIndexer(session, get_embedding_provider())
        service = CuratedImportService(session, indexer=indexer)

        outcomes = await service.preview_batch(parsed_inputs) if dry_run else await service.import_batch(parsed_inputs)
        _print_batch_outcomes(outcomes, dry_run=dry_run)

        all_ok = all(o.ok for o in outcomes)
        if not dry_run and all_ok:
            await session.commit()
        return 0 if all_ok else 1


async def main(*, input_path: str | None, batch_path: str | None, dry_run: bool) -> int:
    session_factory = get_session_factory()
    if batch_path is not None:
        return await _run_batch(session_factory, batch_path=batch_path, dry_run=dry_run)
    return await _run_single(session_factory, input_path=input_path, dry_run=dry_run)  # type: ignore[arg-type]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--input", help="Path to a single input JSON file (see module docstring for shape)")
    source_group.add_argument("--batch", help="Path to a JSONL file, one document per line, same shape as --input")
    parser.add_argument("--dry-run", action="store_true", help="Preview only — no database writes")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(input_path=args.input, batch_path=args.batch, dry_run=args.dry_run)))
