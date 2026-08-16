"""Deterministic contradiction detection — Phase 9.3 brief §14. Runs BEFORE
any LLM involvement (there is no LLM involvement this phase at all — see
module-level scope note below): two canonical facts of the same type whose
values genuinely differ are a contradiction candidate by construction, no
model judgment required.

Scope, stated plainly (brief §14 asks for dates/amounts/party names/document
numbers/performance status — this implements two of the five):

  DATE_MISMATCH — real, via event-type grouping (`app/domains/litigation/
    timeline_builder.py`'s keyword classifier, reused so a "delivery" date
    from an email and a differently-dated "delivery" date from an
    acceptance act are recognized as describing the same kind of event and
    therefore comparable).
  AMOUNT_MISMATCH — real, but bounded: every AMOUNT fact in a case is
    compared against every other (no per-issue/per-line-item grouping,
    since that needs the claim/issue model this phase doesn't build) —
    values within the same order of magnitude (ratio <= 5x) and NOT
    identical are flagged. This deliberately catches the brief's own
    worked example (invoice 500,000 vs acceptance act 450,000) without
    needing document-role-aware grouping this phase doesn't have wired in.
  PARTY_MISMATCH / document-number / performance-status — NOT implemented
    this phase; flagging party-name variants deterministically risks a high
    false-positive rate (legitimate abbreviations, legal-entity-form
    variants) without a real normalization model, so it's left undone
    rather than shipped noisy.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from app.domains.litigation.fact_dedup import CanonicalFact
from app.domains.litigation.timeline_builder import infer_event_type
from app.models.matters import ContradictionType, FactType

_MAX_AMOUNT_RATIO = 5.0


@dataclass
class ContradictionCandidate:
    contradiction_type: ContradictionType
    fact_a: CanonicalFact
    fact_b: CanonicalFact
    description: str


def _detect_date_mismatches(date_facts: list[CanonicalFact]) -> list[ContradictionCandidate]:
    by_event_type: dict[str, list[CanonicalFact]] = {}
    for fact in date_facts:
        event_type = infer_event_type(fact)
        if event_type is not None:
            by_event_type.setdefault(event_type, []).append(fact)

    candidates: list[ContradictionCandidate] = []
    for event_type, facts in by_event_type.items():
        distinct_values = {f.normalized_value for f in facts}
        if len(distinct_values) < 2:
            continue
        for fact_a, fact_b in combinations(facts, 2):
            if fact_a.normalized_value == fact_b.normalized_value:
                continue
            candidates.append(
                ContradictionCandidate(
                    ContradictionType.DATE_MISMATCH, fact_a, fact_b,
                    f"Documents disagree on the '{event_type}' date: {fact_a.normalized_value} vs {fact_b.normalized_value}",
                )
            )
    return candidates


def _detect_amount_mismatches(amount_facts: list[CanonicalFact]) -> list[ContradictionCandidate]:
    candidates: list[ContradictionCandidate] = []
    for fact_a, fact_b in combinations(amount_facts, 2):
        if fact_a.normalized_value == fact_b.normalized_value:
            continue
        value_a, value_b = float(fact_a.normalized_value), float(fact_b.normalized_value)
        if value_a <= 0 or value_b <= 0:
            continue
        ratio = max(value_a, value_b) / min(value_a, value_b)
        if ratio <= _MAX_AMOUNT_RATIO:
            candidates.append(
                ContradictionCandidate(
                    ContradictionType.AMOUNT_MISMATCH, fact_a, fact_b,
                    f"Documents disagree on an amount of similar magnitude: {fact_a.normalized_value} vs {fact_b.normalized_value}",
                )
            )
    return candidates


def detect_contradictions(canonical_facts: list[CanonicalFact]) -> list[ContradictionCandidate]:
    date_facts = [f for f in canonical_facts if f.fact_type == FactType.DATE]
    amount_facts = [f for f in canonical_facts if f.fact_type == FactType.AMOUNT]
    return _detect_date_mismatches(date_facts) + _detect_amount_mismatches(amount_facts)
