"""Deterministic chronology — Phase 9.3 brief §10/§11. Builds a sorted
timeline from the case's canonical DATE facts (`app/domains/litigation/
fact_dedup.py`). Only `EXACT` and `UNKNOWN` date types are ever produced —
`CALCULATED` (deriving a date from a rule like "within 10 business days of
delivery") and `APPROXIMATE` are modeled in the schema for forward
compatibility but no code path here emits them; a `CalculatedDate` engine
would need real date-arithmetic-from-legal-text parsing this phase doesn't
attempt (documented limitation, not silently pretended away).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.domains.litigation.fact_dedup import CanonicalFact
from app.models.matters import DateType

_EVENT_TYPE_KEYWORDS: dict[str, list[str]] = {
    "contract_signed": ["подписан", "заключ"],
    "delivery": ["поставк", "передач", "доставк", "получ"],
    "payment": ["оплат", "платеж", "перечисл"],
    "demand": ["претензи", "требован"],
    "response": ["ответ на претензию", "возражени"],
    "acceptance": ["приёмк", "приемк", "акт"],
}


@dataclass
class TimelineEventDraft:
    event_date: date | None
    date_type: DateType
    description: str
    event_type: str | None
    source_fact: CanonicalFact


def infer_event_type(fact: CanonicalFact) -> str | None:
    haystack = " ".join(e.excerpt.lower() for e in fact.evidence)
    for event_type, keywords in _EVENT_TYPE_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return event_type
    return None


def build_timeline(canonical_date_facts: list[CanonicalFact]) -> list[TimelineEventDraft]:
    events: list[TimelineEventDraft] = []
    for fact in canonical_date_facts:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", fact.normalized_value)
        if not match:
            events.append(TimelineEventDraft(None, DateType.UNKNOWN, fact.statement, None, fact))
            continue
        year, month, day = (int(g) for g in match.groups())
        try:
            event_date = date(year, month, day)
        except ValueError:
            events.append(TimelineEventDraft(None, DateType.UNKNOWN, fact.statement, None, fact))
            continue
        events.append(TimelineEventDraft(event_date, DateType.EXACT, fact.statement, infer_event_type(fact), fact))

    # Deterministic sort: dated events chronologically first, undated events
    # last (by statement text, so the ordering is stable and reproducible,
    # never "whatever order the DB returned them in").
    return sorted(events, key=lambda e: (e.event_date is None, e.event_date or date.min, e.description))
