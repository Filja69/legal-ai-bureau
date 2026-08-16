"""Recall@k / MRR / Citation Recall computation for the retrieval benchmark
(Phase 5 brief §30-35). Kept as a standalone, dependency-free module so the
same functions can score a "mock" run and a "real" run identically and the
two numbers are directly comparable — no metric-definition drift between runs.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QueryScore:
    case_id: str
    category: str
    metric: str  # "retrieval" | "citation"
    hit_rank: int | None  # 1-indexed rank of the first expected identifier found; None if never found
    citation_correct: bool | None = None  # for metric == "citation": did status match expectation?


def recall_at_k(scores: list[QueryScore], k: int) -> float:
    retrieval = [s for s in scores if s.metric == "retrieval"]
    if not retrieval:
        return 0.0
    hits = sum(1 for s in retrieval if s.hit_rank is not None and s.hit_rank <= k)
    return hits / len(retrieval)


def mean_reciprocal_rank(scores: list[QueryScore]) -> float:
    retrieval = [s for s in scores if s.metric == "retrieval"]
    if not retrieval:
        return 0.0
    return sum((1.0 / s.hit_rank) if s.hit_rank else 0.0 for s in retrieval) / len(retrieval)


def citation_recall(scores: list[QueryScore]) -> float:
    citation = [s for s in scores if s.metric == "citation"]
    if not citation:
        return 0.0
    return sum(1 for s in citation if s.citation_correct) / len(citation)


def summarize(scores: list[QueryScore]) -> dict:
    return {
        "n_retrieval_queries": len([s for s in scores if s.metric == "retrieval"]),
        "n_citation_queries": len([s for s in scores if s.metric == "citation"]),
        "recall_at_1": round(recall_at_k(scores, 1), 4),
        "recall_at_5": round(recall_at_k(scores, 5), 4),
        "recall_at_10": round(recall_at_k(scores, 10), 4),
        "mrr": round(mean_reciprocal_rank(scores), 4),
        "citation_recall": round(citation_recall(scores), 4),
    }


def summarize_by_category(scores: list[QueryScore]) -> dict[str, dict]:
    categories = sorted({s.category for s in scores})
    return {cat: summarize([s for s in scores if s.category == cat]) for cat in categories}
