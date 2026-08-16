"""TemporalConsistencyChecker + issue-type classification — brief §29-30.

Deterministic, not LLM-driven: (1) defense-in-depth check that every
law_version piece of evidence actually falls within its claimed validity
window at the requested effective_at (the retrieval filter should already
guarantee this — this re-checks it rather than trusting that guarantee
silently); (2) a lightweight keyword heuristic distinguishing substantive
from procedural issues, since "does the right exist" and "can it currently
be exercised procedurally" are different questions per the brief.
"""
from __future__ import annotations

from datetime import date

from app.domains.legal_research.models import EvidenceItem, IssueType

_PROCEDURAL_KEYWORDS = (
    "срок исковой давности", "подсудность", "процессуальн", "порядок обжалования",
    "исполнительное производство", "апелляц", "кассац", "судебн", "иск подан", "уведомлени",
)


def classify_issue_type(title: str, description: str) -> IssueType:
    text = f"{title} {description}".lower()
    return IssueType.PROCEDURAL if any(kw in text for kw in _PROCEDURAL_KEYWORDS) else IssueType.SUBSTANTIVE


class TemporalConsistencyChecker:
    def check(self, evidence: list[EvidenceItem], effective_at: date | None) -> list[str]:
        if effective_at is None:
            return []

        warnings: list[str] = []
        for item in evidence:
            if item.metadata.get("chunk_type") != "law_version":
                continue
            effective_from = item.metadata.get("effective_from")
            effective_to = item.metadata.get("effective_to")
            as_of = effective_at.isoformat()

            if effective_from and as_of < effective_from:
                warnings.append(f"{item.citation}: retrieved version takes effect {effective_from}, after the requested date {as_of}.")
            if effective_to and as_of >= effective_to:
                warnings.append(f"{item.citation}: retrieved version expired {effective_to}, before/at the requested date {as_of}.")
        return warnings
