"""Deterministic fact deduplication — Phase 9.3 brief §9. Different
documents (contract, invoice, correspondence) often restate the same
event/date/amount; this groups raw `FactCandidate`s that share a
`(fact_type, normalized_value)` key into one canonical fact backed by every
contributing document, rather than N unrelated facts.

This is a deterministic baseline only — string/number normalization, not
semantic similarity. A genuinely different phrasing of the same fact that
normalizes to a different canonical value (e.g. a typo'd date) will NOT be
merged; a real semantic-dedup pass would need embeddings or an LLM call,
neither of which is wired into this deterministic layer (documented
limitation, not silently pretended away — see
docs/PHASE-9-3-LITIGATION-RESULT.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.litigation.fact_extractor import FactCandidate, FactEvidenceCandidate
from app.models.matters import FactType


@dataclass
class CanonicalFact:
    fact_type: FactType
    statement: str
    normalized_value: str
    evidence: list[FactEvidenceCandidate] = field(default_factory=list)

    @property
    def corroboration_count(self) -> int:
        """Number of distinct documents supporting this fact — the
        deterministic input to evidence-matrix strength scoring
        (app/domains/litigation/evidence_matrix.py), not an LLM guess.
        """
        return len({e.document_id for e in self.evidence})


def deduplicate_facts(candidates: list[FactCandidate]) -> list[CanonicalFact]:
    groups: dict[tuple[FactType, str], CanonicalFact] = {}
    for candidate in candidates:
        key = (candidate.fact_type, candidate.normalized_value)
        canonical = groups.get(key)
        if canonical is None:
            canonical = CanonicalFact(
                fact_type=candidate.fact_type, statement=candidate.statement, normalized_value=candidate.normalized_value
            )
            groups[key] = canonical
        canonical.evidence.append(candidate.evidence)
    return list(groups.values())
