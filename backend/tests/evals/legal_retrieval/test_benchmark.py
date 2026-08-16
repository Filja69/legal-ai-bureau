"""Phase 5 quantitative retrieval benchmark (brief §30-35). Runs every
categorized case_*.json (the 55 cases generate_cases.py writes, plus any
future additions) through keyword-only, vector-only, and hybrid retrieval,
scores each with metrics.py, and writes a JSON report per mode+embedding
provider to results/. This is deliberately NOT a hard pass/fail gate —
see test_eval_cases.py for the strict regression gate. A low number here is
a valid, reportable outcome (per brief §35 "if no improvement, say so"), not
a test failure to be hidden.

Run directly for a human-readable report:
    pytest tests/evals/legal_retrieval/test_benchmark.py -s
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.hybrid_retriever import HybridRetriever
from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever
from app.rag.retrieval.vector_retriever import PgVectorRetriever
from app.rag.validation.citation_validator import CitationDraft, CitationValidator
from app.sources.mock.mock_source import MockLegalDataSource
from tests.evals.legal_retrieval.metrics import QueryScore, summarize, summarize_by_category

_CASES_DIR = Path(__file__).parent
_RESULTS_DIR = _CASES_DIR / "results"
_BENCHMARK_TOP_K = 20  # generous — we want the true rank, not just a pass/fail at the case's own top_k
_CITATION_RE = re.compile(r"(?P<law>[^,]+?),?\s*ст(?:атья|\.)?\s*(?P<article>\d+)", re.IGNORECASE)


def _load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _categorized_cases() -> list[Path]:
    return sorted(p for p in _CASES_DIR.glob("case_*.json") if "category" in _load_case(p))


@pytest.fixture
async def indexed_dataset(db_session):
    source = LegalSource(name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, is_mock=True)
    db_session.add(source)
    await db_session.flush()
    indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider())
    pipeline = IngestionPipeline(
        db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator(), indexer=indexer
    )
    await pipeline.ingest_source(source)
    await db_session.commit()
    return source


def _hit_rank(results, expected_articles: list[str], expected_case_numbers: list[str]) -> int | None:
    expected = set(expected_articles) | set(expected_case_numbers)
    if not expected:
        return None
    found_at: dict[str, int] = {}
    for rank, r in enumerate(results, start=1):
        for ident in (r.metadata.get("article_number"), r.metadata.get("case_number")):
            if ident in expected and ident not in found_at:
                found_at[ident] = rank
    if len(found_at) < len(expected):
        return None  # not everything required was retrieved within top_k — a genuine miss
    return max(found_at.values())


async def _score_mode(db_session, cases: list[dict], retriever) -> list[QueryScore]:
    scores: list[QueryScore] = []
    validator = CitationValidator(db_session)
    for case in cases:
        if "citation_text" in case:
            match = _CITATION_RE.search(case["citation_text"])
            if not match:
                continue
            check = await validator.validate(
                CitationDraft(law_short_name=match.group("law").strip(), article_number=match.group("article"), quoted_fragment=None)
            )
            scores.append(QueryScore(
                case_id=case["case_id"], category=case["category"], metric="citation",
                hit_rank=None, citation_correct=check.status.value == case["expected_citation_status"],
            ))
            continue

        results = await retriever.retrieve(
            RetrievalQuery(text=case["query"], event_date=case.get("effective_at"), top_k=_BENCHMARK_TOP_K)
        )
        rank = _hit_rank(results, case.get("expected_articles", []), case.get("expected_case_numbers", []))
        scores.append(QueryScore(case_id=case["case_id"], category=case["category"], metric="retrieval", hit_rank=rank))
    return scores


@pytest.mark.asyncio
async def test_retrieval_benchmark_mock_embeddings(db_session, indexed_dataset):
    cases = [_load_case(p) for p in _categorized_cases()]
    embedding_provider = MockEmbeddingProvider()

    modes = {
        "keyword": PostgresKeywordRetriever(db_session),
        "vector": PgVectorRetriever(db_session, embedding_provider),
        "hybrid": HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, embedding_provider)),
    }

    report: dict = {"embedding_provider": embedding_provider.model_name, "n_cases": len(cases), "modes": {}}
    for mode_name, retriever in modes.items():
        scores = await _score_mode(db_session, cases, retriever)
        report["modes"][mode_name] = {"overall": summarize(scores), "by_category": summarize_by_category(scores)}

    _RESULTS_DIR.mkdir(exist_ok=True)
    (_RESULTS_DIR / "baseline_mock.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + json.dumps(report["modes"]["hybrid"]["overall"], ensure_ascii=False, indent=2))

    # Sanity floor only — this is a benchmark, not a strict gate (brief §35:
    # a low number is a valid, reportable result). We only assert the
    # harness itself produced *some* signal, not that mock scored well.
    assert report["n_cases"] >= 50
    hybrid_overall = report["modes"]["hybrid"]["overall"]
    assert hybrid_overall["n_retrieval_queries"] + hybrid_overall["n_citation_queries"] == len(cases)
