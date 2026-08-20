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

import uuid
from dataclasses import dataclass
from datetime import date
from itertools import combinations

from app.domains.litigation.fact_dedup import CanonicalFact
from app.domains.litigation.timeline_builder import infer_event_type
from app.models.matters import AllegationType, ContradictionType, FactType

_MAX_AMOUNT_RATIO = 5.0

_FORMATION_CAVEAT = "This evidence does not by itself establish that the contract was legally concluded."


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


# --- CLAIM_VS_EVIDENCE (E2, litigation evidence-layer brief) ---
#
# Computed at read time, never persisted as a CaseContradiction row (see
# ContradictionType.CLAIM_VS_EVIDENCE's docstring in app/models/matters.py) —
# same "computed, not schema-exploded" choice as evidence_matrix.py.
#
# The rule is deliberately narrow and additive-only: a NO_CONTRACT allegation
# cross-referenced against a payment order whose payment_purpose names a
# specific loan agreement + date. It NEVER concludes the contract WAS
# concluded — every result carries an explicit caveat saying so, and the
# `reason` text is phrased as "relevant evidence", not a verdict. A payment
# order whose purpose mentions some OTHER kind of contract (e.g. "договор
# поставки") never enters `loan_payments` at all, because
# payment_extractor.py only populates referenced_contract_type/date for
# payments that matched the loan-specific pattern — see its own docstring
# and the false-positive regression test.


@dataclass
class AllegationInput:
    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int | None
    excerpt: str
    allegation_type: AllegationType


@dataclass
class PaymentOrderInput:
    id: uuid.UUID
    document_id: uuid.UUID
    page_number: int | None
    excerpt: str
    referenced_contract_type: str | None
    referenced_contract_date: date | None


@dataclass
class ClaimEvidenceContradiction:
    allegation_id: uuid.UUID
    allegation_document_id: uuid.UUID
    allegation_page: int | None
    allegation_excerpt: str
    evidence_id: uuid.UUID
    evidence_document_id: uuid.UUID
    evidence_page: int | None
    evidence_excerpt: str
    referenced_contract_date: date | None
    reason: str
    contradiction_type: ContradictionType = ContradictionType.CLAIM_VS_EVIDENCE
    caveat: str = _FORMATION_CAVEAT
    confidence: str = "Based only on the documented evidence above, not model inference."


def detect_claim_vs_evidence_contradictions(
    allegations: list[AllegationInput], payment_orders: list[PaymentOrderInput]
) -> list[ClaimEvidenceContradiction]:
    no_contract_allegations = [a for a in allegations if a.allegation_type == AllegationType.NO_CONTRACT]
    loan_payments = [
        p for p in payment_orders if p.referenced_contract_type is not None and p.referenced_contract_date is not None
    ]

    candidates: list[ClaimEvidenceContradiction] = []
    for allegation in no_contract_allegations:
        for payment in loan_payments:
            contract_date = payment.referenced_contract_date
            assert contract_date is not None  # guaranteed by the loan_payments filter above
            candidates.append(
                ClaimEvidenceContradiction(
                    allegation_id=allegation.id,
                    allegation_document_id=allegation.document_id,
                    allegation_page=allegation.page_number,
                    allegation_excerpt=allegation.excerpt,
                    evidence_id=payment.id,
                    evidence_document_id=payment.document_id,
                    evidence_page=payment.page_number,
                    evidence_excerpt=payment.excerpt,
                    referenced_contract_date=contract_date,
                    reason=(
                        "The payer itself referenced a specific loan agreement "
                        f"(dated {contract_date.isoformat()}) in an executed banking document, "
                        "while the pleading alleges no contract was concluded — this is relevant evidence "
                        "concerning the factual/legal basis of the transfer."
                    ),
                )
            )
    return candidates
