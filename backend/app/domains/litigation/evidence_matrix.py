"""Evidence Matrix — Phase 9.3 brief §12/§13. Explainable, deterministic
strength scoring — never a fabricated percentage (brief: "Evidence strength
= 83%... unless there is an explicit deterministic model behind it").

Scope note: the brief's full factor list (direct/indirect, signed/unsigned,
original/copy, party-authored/third-party, identity established) needs
document-level metadata this phase's `CaseDocument`/`Document` models don't
capture (e.g. nothing here knows if a PDF was actually signed). The two
factors that ARE reliably deterministic from what's already persisted —
corroboration count (how many distinct documents state the same canonical
fact) and whether the fact participates in a detected contradiction — are
what this scorer actually uses. Documented as a real, bounded model, not
disguised as the full brief §13 factor list.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from app.domains.litigation.contradiction_detector import ContradictionCandidate
from app.domains.litigation.fact_dedup import CanonicalFact


class EvidenceStrength(str, enum.Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    CONFLICTED = "conflicted"
    INSUFFICIENT = "insufficient"


@dataclass
class EvidenceMatrixRow:
    fact: CanonicalFact
    strength: EvidenceStrength
    reasons: list[str] = field(default_factory=list)


def build_evidence_matrix(
    canonical_facts: list[CanonicalFact], contradictions: list[ContradictionCandidate]
) -> list[EvidenceMatrixRow]:
    contradicted_values: set[tuple] = set()
    for c in contradictions:
        contradicted_values.add((c.fact_a.fact_type, c.fact_a.normalized_value))
        contradicted_values.add((c.fact_b.fact_type, c.fact_b.normalized_value))

    rows: list[EvidenceMatrixRow] = []
    for fact in canonical_facts:
        reasons: list[str] = []
        if (fact.fact_type, fact.normalized_value) in contradicted_values:
            strength = EvidenceStrength.CONFLICTED
            reasons.append("Contradicted by another document in this case")
        elif fact.corroboration_count >= 2:
            strength = EvidenceStrength.STRONG
            reasons.append(f"Corroborated by {fact.corroboration_count} independent documents")
        elif fact.corroboration_count == 1:
            strength = EvidenceStrength.MODERATE
            reasons.append("Supported by a single document — not independently corroborated")
        else:  # pragma: no cover — a canonical fact always has >=1 evidence row by construction
            strength = EvidenceStrength.INSUFFICIENT
            reasons.append("No supporting evidence")
        rows.append(EvidenceMatrixRow(fact=fact, strength=strength, reasons=reasons))
    return rows
