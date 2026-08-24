"""Case Intelligence — party/corporate relationships, temporal analysis,
and the client-facing "Связи сторон и обстоятельства, требующие проверки"
section. Pure functions only, same discipline as every other module in this
package: no DB access, no LLM calls, nothing here ever concludes a party
"knew" something — every relationship-timing result carries an explicit
caveat regardless of how the timing lines up, because status (director,
shareholder, member) is never, by itself, evidence of actual knowledge.

Related-litigation notes follow the same discipline: the timing/existence
of another matter is presented as context worth investigating, never as a
claimed cause of the present case (see brief: "the claimant filed this
action because it needs money" is the exact sentence this module must never
produce).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.models.matters import HypothesisCategory, RelationshipType, RelationshipVerificationStatus

_ACTIVE_AT_DATE_CAVEAT = (
    "This relationship may be relevant to assessing the claimant's knowledge, but does not by itself "
    "establish actual knowledge of the transaction."
)
_NOT_YET_ACTIVE_CAVEAT = (
    "At this date the relationship had not yet begun according to the recorded start date — this weighs "
    "against (but does not itself disprove) relevance to knowledge at that time."
)
_ENDED_BEFORE_CAVEAT = (
    "At this date the relationship had already ended according to the recorded end date — this weighs "
    "against (but does not itself disprove) relevance to knowledge at that time."
)
_UNKNOWN_TIMING_CAVEAT = (
    "The relationship's timing relative to this date cannot be determined from the documents currently "
    "available — this is an open question, not an established fact either way."
)

_DEFAULT_REQUIRED_VERIFICATION = [
    "История ЕГРЮЛ (EGRUL history)",
    "Реестр участников / реестр акционеров",
    "Запросы о предоставлении корпоративной информации",
    "Уведомления о собраниях / протоколы собраний",
    "Переписка сторон",
    "Доказательства фактического доступа к информации либо отказа в доступе",
]

_RELATED_LITIGATION_NOTE_TEMPLATE = (
    "Существование и сроки другого судебного дела{case_number_clause} могут потребовать дополнительной "
    "проверки в качестве контекстной информации; имеющиеся доказательства не подтверждают, что оно "
    "стало причиной настоящего иска."
)


@dataclass
class RelationshipTimingResult:
    status: str  # "active_at_date" | "not_yet_active" | "ended_before" | "unknown_timing"
    caveat: str


def classify_relationship_timing(start_date: date | None, end_date: date | None, target_date: date | None) -> RelationshipTimingResult:
    """Never returns a bare "yes"/"no" — every branch's caveat makes explicit
    that timing overlap is not knowledge. `target_date` is typically a
    payment date or another case-significant date being cross-referenced.
    """
    if target_date is None or (start_date is None and end_date is None):
        return RelationshipTimingResult("unknown_timing", _UNKNOWN_TIMING_CAVEAT)
    if start_date is not None and target_date < start_date:
        return RelationshipTimingResult("not_yet_active", _NOT_YET_ACTIVE_CAVEAT)
    if end_date is not None and target_date > end_date:
        return RelationshipTimingResult("ended_before", _ENDED_BEFORE_CAVEAT)
    if start_date is not None:
        return RelationshipTimingResult("active_at_date", _ACTIVE_AT_DATE_CAVEAT)
    return RelationshipTimingResult("unknown_timing", _UNKNOWN_TIMING_CAVEAT)


def build_related_litigation_note(case_number: str | None) -> str:
    case_number_clause = f" ({case_number})" if case_number else ""
    return _RELATED_LITIGATION_NOTE_TEMPLATE.format(case_number_clause=case_number_clause)


# --- Client-facing synthesis ---


@dataclass
class CasePartyRelationshipInput:
    id: uuid.UUID
    subject_party_id: uuid.UUID
    subject_name: str
    related_party_id: uuid.UUID
    related_party_name: str
    relationship_type: RelationshipType
    start_date: date | None
    end_date: date | None
    verification_status: RelationshipVerificationStatus
    source_document_id: uuid.UUID | None
    source_excerpt: str | None


@dataclass
class CaseHypothesisInput:
    id: uuid.UUID
    category: HypothesisCategory
    statement: str
    required_verification: list[str]
    related_relationship_id: uuid.UUID | None


@dataclass
class PartyRelationshipFinding:
    subject_name: str
    related_party_name: str
    relationship_type: RelationshipType
    relationship_start: date | None
    relationship_end: date | None
    timing_note: str
    why_it_may_matter: str
    what_is_still_needed: list[str] = field(default_factory=list)
    verification_status: RelationshipVerificationStatus = RelationshipVerificationStatus.UNVERIFIED
    source_document_id: uuid.UUID | None = None
    source_document_title: str | None = None
    source_excerpt: str | None = None


_RELATIONSHIP_TYPE_LABEL: dict[RelationshipType, str] = {
    RelationshipType.DIRECTOR: "директор",
    RelationshipType.SHAREHOLDER: "акционер",
    RelationshipType.MEMBER: "участник",
    RelationshipType.OTHER: "связанное лицо",
}


def _timing_summary(start: date | None, reference_dates: list[date]) -> str:
    if start is None:
        return "Дата возникновения связи в материалах не установлена."
    if not reference_dates:
        return f"Дата возникновения связи: {start.isoformat()}."
    earliest, latest = min(reference_dates), max(reference_dates)
    timing = classify_relationship_timing(start, None, earliest)
    return (
        f"Дата возникновения связи: {start.isoformat()}. Платежи по делу: {earliest.isoformat()}"
        f"{' — ' + latest.isoformat() if latest != earliest else ''}. {timing.caveat}"
    )


def build_party_relationship_findings(
    relationships: list[CasePartyRelationshipInput],
    reference_dates: list[date],
    hypotheses: list[CaseHypothesisInput],
    document_titles: dict[uuid.UUID, str],
) -> list[PartyRelationshipFinding]:
    """One finding per relationship, capped at 5 to match the discipline
    already established for key_findings in case_result_summary.py — the
    client-facing section is a highlight list, not a data dump.
    """
    hypotheses_by_relationship: dict[uuid.UUID, list[CaseHypothesisInput]] = {}
    for h in hypotheses:
        if h.related_relationship_id is not None:
            hypotheses_by_relationship.setdefault(h.related_relationship_id, []).append(h)

    findings: list[PartyRelationshipFinding] = []
    for rel in relationships:
        linked_hypotheses = hypotheses_by_relationship.get(rel.id, [])
        required_verification: list[str] = []
        for h in linked_hypotheses:
            required_verification.extend(h.required_verification)
        if not required_verification:
            required_verification = list(_DEFAULT_REQUIRED_VERIFICATION)

        role_label = _RELATIONSHIP_TYPE_LABEL[rel.relationship_type]
        findings.append(
            PartyRelationshipFinding(
                subject_name=rel.subject_name,
                related_party_name=rel.related_party_name,
                relationship_type=rel.relationship_type,
                relationship_start=rel.start_date,
                relationship_end=rel.end_date,
                timing_note=_timing_summary(rel.start_date, reference_dates),
                why_it_may_matter=(
                    f"{rel.subject_name} — {role_label} «{rel.related_party_name}». "
                    "Это может иметь значение для оценки осведомлённости и поведения соответствующей стороны."
                ),
                what_is_still_needed=required_verification,
                verification_status=rel.verification_status,
                source_document_id=rel.source_document_id,
                source_document_title=document_titles.get(rel.source_document_id, None) if rel.source_document_id else None,
                source_excerpt=rel.source_excerpt,
            )
        )
    return findings[:5]
