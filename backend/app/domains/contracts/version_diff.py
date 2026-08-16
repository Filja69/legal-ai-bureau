"""Contract version comparison — brief §50-51. Clause matching is by
`clause_number` when present (stable across edits), falling back to exact
`normalized_text` match — never fuzzy/LLM matching, so "added/removed/changed"
is always reproducible from the same two versions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.contracts.structure_extractor import ExtractedClause
from app.domains.contracts.two_lawyer_review import ReviewedRisk


@dataclass
class ClauseDiff:
    added: list[ExtractedClause] = field(default_factory=list)
    removed: list[ExtractedClause] = field(default_factory=list)
    changed: list[tuple[ExtractedClause, ExtractedClause]] = field(default_factory=list)  # (old, new)
    unchanged_count: int = 0


def _clause_key(clause: ExtractedClause) -> str:
    return clause.clause_number or clause.normalized_text[:80]


def diff_clauses(old_clauses: list[ExtractedClause], new_clauses: list[ExtractedClause]) -> ClauseDiff:
    old_by_key = {_clause_key(c): c for c in old_clauses}
    new_by_key = {_clause_key(c): c for c in new_clauses}

    diff = ClauseDiff()
    for key, new_clause in new_by_key.items():
        old_clause = old_by_key.get(key)
        if old_clause is None:
            diff.added.append(new_clause)
        elif old_clause.normalized_text != new_clause.normalized_text:
            diff.changed.append((old_clause, new_clause))
        else:
            diff.unchanged_count += 1

    for key, old_clause in old_by_key.items():
        if key not in new_by_key:
            diff.removed.append(old_clause)

    return diff


@dataclass
class RiskDiff:
    new_risks: list[ReviewedRisk] = field(default_factory=list)
    resolved_risks: list[ReviewedRisk] = field(default_factory=list)
    persisting_risks: list[ReviewedRisk] = field(default_factory=list)


def _risk_key(risk: ReviewedRisk) -> tuple:
    candidate = risk.verified_risk.candidate
    return (candidate.detector, candidate.risk_type, candidate.title)


def diff_risks(old_risks: list[ReviewedRisk], new_risks: list[ReviewedRisk]) -> RiskDiff:
    old_by_key = {_risk_key(r): r for r in old_risks}
    new_by_key = {_risk_key(r): r for r in new_risks}

    diff = RiskDiff()
    for key, risk in new_by_key.items():
        if key in old_by_key:
            diff.persisting_risks.append(risk)
        else:
            diff.new_risks.append(risk)
    for key, risk in old_by_key.items():
        if key not in new_by_key:
            diff.resolved_risks.append(risk)
    return diff
