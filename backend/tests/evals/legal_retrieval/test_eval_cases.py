"""AI evaluation benchmark — LEGAL-ROADMAP.md §Testing strategy, Phase 2 brief §37.

Each case_NNN.json is a deterministic, hand-authored expectation against the
mock legal dataset — not a measure of "is this good AI," since there's no AI
reasoning yet (Phase 2 is retrieval-only). This is the retrieval-accuracy
half of the eventual eval suite: does hybrid search / temporal filtering /
citation validation return what it should, and only what it should.
"""
from __future__ import annotations

import json
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

_CASES_DIR = Path(__file__).parent
_ALL_CASES = sorted(_CASES_DIR.glob("case_*.json"))


def _load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# Phase 2's original 6 cases (no "category" field) are the strict regression
# gate — narrow top_k, must always pass under mock embeddings, block `pytest`
# on failure. The Phase 5 benchmark cases (55 more, each tagged with a
# "category") measure retrieval quality quantitatively instead — see
# test_benchmark.py. They deliberately are NOT part of this strict gate:
# MockEmbeddingProvider's vector leg is non-semantic noise (LEGAL-RAG.md
# REAL/MOCK split), so at realistic top_k values several of them are
# *expected* to miss under mock — that's the honest baseline the benchmark
# exists to report, not a regression to hide by loosening this gate.
_RETRIEVAL_CASES = [p for p in _ALL_CASES if "category" not in _load_case(p)]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("case_path", _RETRIEVAL_CASES, ids=lambda p: p.stem)
async def test_retrieval_eval_case(db_session, indexed_dataset, case_path):
    case = _load_case(case_path)

    if "citation_text" in case:
        validator = CitationValidator(db_session)
        # crude inline parse — mirrors app/api/v1/knowledge.py's verify_citation regex
        import re

        match = re.search(r"(?P<law>[^,]+?),?\s*ст(?:атья|\.)?\s*(?P<article>\d+)", case["citation_text"], re.IGNORECASE)
        assert match, f"{case['case_id']}: could not parse citation_text"
        check = await validator.validate(
            CitationDraft(law_short_name=match.group("law").strip(), article_number=match.group("article"), quoted_fragment=None)
        )
        assert check.status.value == case["expected_citation_status"], f"{case['case_id']}: {check.reason}"
        return

    hybrid = HybridRetriever(PostgresKeywordRetriever(db_session), PgVectorRetriever(db_session, MockEmbeddingProvider()))
    results = await hybrid.retrieve(
        RetrievalQuery(text=case["query"], event_date=case.get("effective_at"), top_k=case.get("top_k", 10))
    )

    returned_articles = {r.metadata.get("article_number") for r in results if r.metadata.get("article_number")}
    returned_case_numbers = {r.metadata.get("case_number") for r in results if r.metadata.get("case_number")}

    for expected in case.get("expected_articles", []):
        assert expected in returned_articles, f"{case['case_id']}: expected article {expected} not found in {returned_articles}"

    for expected_case_number in case.get("expected_case_numbers", []):
        assert expected_case_number in returned_case_numbers, (
            f"{case['case_id']}: expected case {expected_case_number} not found in {returned_case_numbers}"
        )

    for forbidden in case.get("must_not_return_articles", []):
        assert forbidden not in returned_articles, f"{case['case_id']}: forbidden article {forbidden} was returned"

    if "expected_effective_to" in case:
        matching = [r for r in results if r.metadata.get("article_number") == case["expected_articles"][0]]
        assert len(matching) == 1, f"{case['case_id']}: expected exactly one matching version at this date"
        assert matching[0].metadata.get("effective_to") == case["expected_effective_to"]


def test_eval_dataset_is_non_empty():
    assert len(_RETRIEVAL_CASES) >= 5, "Expected at least 5 deterministic eval cases (brief §37)"


def test_benchmark_dataset_has_at_least_50_cases():
    # Phase 5 brief §31 — the Phase 2 regression cases plus the Phase 5
    # benchmark cases together must reach the 50-query minimum.
    assert len(_ALL_CASES) >= 50


def test_benchmark_dataset_covers_all_8_categories():
    categories = {_load_case(p).get("category") for p in _ALL_CASES if "category" in _load_case(p)}
    assert categories == {
        "exact_article", "semantic_paraphrase", "multi_concept", "temporal",
        "court_practice", "conflicting_practice", "contract_risk", "adversarial",
    }
