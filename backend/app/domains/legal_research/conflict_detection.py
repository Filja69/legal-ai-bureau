"""LegalConflictDetector — brief §26-28. Deterministic, rule-based — conflict
detection does not depend on LLM quality; it compares structured evidence
(outcomes, article versions) directly, which is both more reliable and
honestly available even under LLM_PROVIDER=mock.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_research.models import ConflictType, EvidenceItem, LegalConflict
from app.models.case_law import CourtDecision


class LegalConflictDetector:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def detect(self, evidence: list[EvidenceItem]) -> list[LegalConflict]:
        conflicts: list[LegalConflict] = []
        conflicts.extend(await self._detect_jurisprudential_conflict(evidence))
        conflicts.extend(_detect_temporal_conflict(evidence))
        return conflicts

    async def _detect_jurisprudential_conflict(self, evidence: list[EvidenceItem]) -> list[LegalConflict]:
        court_items = [e for e in evidence if e.metadata.get("chunk_type") == "court_decision" and e.metadata.get("court_decision_id")]
        if len(court_items) < 2:
            return []

        # Batched (Phase 6.5 brief §16 N+1 audit) — one query for every
        # court decision in this evidence set instead of one per item.
        decision_ids = [item.metadata["court_decision_id"] for item in court_items]
        result = await self._session.execute(
            select(CourtDecision.id, CourtDecision.outcome).where(CourtDecision.id.in_(decision_ids))
        )
        outcome_by_id = {str(row.id): row.outcome for row in result.all()}

        by_outcome: dict[str, list[EvidenceItem]] = defaultdict(list)
        for item in court_items:
            outcome = outcome_by_id.get(str(item.metadata["court_decision_id"]))
            if outcome:
                by_outcome[outcome].append(item)

        distinct_outcomes = list(by_outcome.keys())
        if len(distinct_outcomes) < 2:
            return []

        outcome_a, outcome_b = distinct_outcomes[0], distinct_outcomes[1]
        return [
            LegalConflict(
                conflict_type=ConflictType.JURISPRUDENTIAL_CONFLICT,
                description="Retrieved court decisions reach different outcomes on related matters.",
                position_a=f"{outcome_a}: " + "; ".join(i.citation for i in by_outcome[outcome_a]),
                position_b=f"{outcome_b}: " + "; ".join(i.citation for i in by_outcome[outcome_b]),
                implication=(
                    "Практика неоднородна — итоговый вывод должен явно учитывать оба направления "
                    "практики, а не выбирать одно молча (LEGAL-RAG.md §6)."
                ),
            )
        ]


def _detect_temporal_conflict(evidence: list[EvidenceItem]) -> list[LegalConflict]:
    """If two different redactions of the SAME article both surfaced in one
    evidence pool (can happen when effective_at wasn't pinned), that's a
    signal the conclusion may be date-sensitive — flag it rather than
    silently picking whichever redaction ranked higher.
    """
    by_article: dict[tuple, list[EvidenceItem]] = defaultdict(list)
    for item in evidence:
        if item.metadata.get("chunk_type") != "law_version":
            continue
        key = (item.metadata.get("law_id"), item.metadata.get("article_number"))
        by_article[key].append(item)

    conflicts = []
    for (_, article), items in by_article.items():
        versions = {i.metadata.get("law_version_id") for i in items}
        if len(versions) < 2:
            continue
        conflicts.append(
            LegalConflict(
                conflict_type=ConflictType.TEMPORAL_CONFLICT,
                description=f"Multiple redactions of article {article} were retrieved without a pinned effective_at.",
                position_a=items[0].text,
                position_b=items[1].text,
                implication="Re-run with an explicit effective_at to resolve which redaction actually applies.",
            )
        )
    return conflicts
