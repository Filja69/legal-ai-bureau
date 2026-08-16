"""Parser/Normalizer/Validator for the mock source's format (brief §12).

The mock source (app/sources/mock/mock_source.py) emits RawDocument.content
as JSON matching app/sources/mock/dataset.py's record shape — since it's a
synthetic dataset we control, there's no messy real-world text to parse.
A real source's parser (Phase 3+, once an official connector exists) would
do actual structure extraction (regex/NLP over "Статья N ..." headers etc.);
this one just deserializes.
"""
from __future__ import annotations

import json
from datetime import date

from app.domains.legal_knowledge.ingestion.protocols import ParsedLegalContent, ValidationResult
from app.sources.base import RawDocument


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class MockSourceParser:
    def parse(self, raw: RawDocument) -> ParsedLegalContent:
        record = json.loads(raw.content)
        if record["kind"] == "law_article":
            return ParsedLegalContent(
                kind="law_article",
                title=record["title"],
                publication_date=_parse_date(record.get("publication_date")),
                effective_date=_parse_date(record.get("effective_date")),
                law_short_name=record["law_short_name"],
                law_full_name=record["law_full_name"],
                code_type=record.get("code_type"),
                article_number=record["article_number"],
                clause_number=record.get("clause_number"),
                text=record["text"],
                hierarchy_path=record.get("hierarchy_path", []),
                valid_from=_parse_date(record["valid_from"]),
                valid_to=_parse_date(record.get("valid_to")),
                amending_act_title=record.get("amending_act_title"),
                amending_act_source_url=record.get("amending_act_source_url"),
            )
        return ParsedLegalContent(
            kind="court_decision",
            title=record["title"],
            publication_date=_parse_date(record.get("publication_date")),
            effective_date=_parse_date(record.get("effective_date")),
            court_name=record["court_name"],
            court_level=record["court_level"],
            case_number=record["case_number"],
            decision_date=_parse_date(record["decision_date"]),
            parties=record.get("parties", {}),
            claim_summary=record.get("claim_summary"),
            decision_summary=record.get("decision_summary"),
            legal_reasoning=record.get("legal_reasoning"),
            outcome=record.get("outcome"),
        )


class MockSourceNormalizer:
    """Whitespace/encoding normalization (brief §6). Mock text is already
    clean, but this still runs so the pipeline behaves identically to how a
    real source's output would be treated — normalization isn't skipped
    just because the input happens to already be tidy.
    """

    def normalize(self, parsed: ParsedLegalContent) -> ParsedLegalContent:
        parsed.title = " ".join(parsed.title.split())
        if parsed.text:
            parsed.text = " ".join(parsed.text.split())
        if parsed.legal_reasoning:
            parsed.legal_reasoning = " ".join(parsed.legal_reasoning.split())
        return parsed


class MockSourceValidator:
    def validate(self, parsed: ParsedLegalContent) -> ValidationResult:
        errors: list[str] = []
        if not parsed.title.strip():
            errors.append("title is required")
        if parsed.kind == "law_article":
            if not parsed.law_short_name:
                errors.append("law_short_name is required for law_article")
            if not parsed.article_number:
                errors.append("article_number is required for law_article")
            if not parsed.text.strip():
                errors.append("text is required for law_article")
            if parsed.valid_from is None:
                errors.append("valid_from is required for law_article")
            elif parsed.valid_to is not None and parsed.valid_to <= parsed.valid_from:
                errors.append(f"valid_to ({parsed.valid_to}) must be after valid_from ({parsed.valid_from})")
        elif parsed.kind == "court_decision":
            if not parsed.case_number:
                errors.append("case_number is required for court_decision")
            if not parsed.court_name:
                errors.append("court_name is required for court_decision")
        return ValidationResult(is_valid=not errors, errors=errors)
