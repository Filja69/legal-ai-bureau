"""LegalResearchEngine — full pipeline integration, brief §2, §31, §36-37, §53."""
from __future__ import annotations

from datetime import date

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.domains.legal_research.engine import LegalResearchEngine
from app.domains.legal_research.models import ClaimVerificationStatus, ConfidenceLevel, LegalResearchRequest
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource


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


def _engine(db_session) -> LegalResearchEngine:
    return LegalResearchEngine(db_session, LLMGateway(provider=MockLLMProvider()))


@pytest.mark.asyncio
async def test_engine_runs_end_to_end_and_returns_structured_result(db_session, indexed_dataset):
    request = LegalResearchRequest(
        question="Может ли заказчик отказаться от договора? надлежащим образом исполнение",
        facts=["договор заключен между ООО и ИП"],
    )
    result, trace = await _engine(db_session).run(request)

    assert result.status in ("completed", "blocked_unverified_claim")
    assert isinstance(result.confidence, ConfidenceLevel)
    assert len(result.issues) >= 1
    assert len(result.facts) == 1
    assert trace.research_id
    assert trace.question == request.question
    assert trace.knowledge_snapshot is not None
    assert trace.knowledge_snapshot.total_chunks > 0


@pytest.mark.asyncio
async def test_engine_finds_verified_mock_citations_for_matching_question(db_session, indexed_dataset):
    request = LegalResearchRequest(question="надлежащим образом исполнение обязательства ст 309")
    result, _ = await _engine(db_session).run(request)

    rule_claims = [c for c in result.claims if c.claim_type == "rule"]
    assert len(rule_claims) >= 1
    assert any(c.verification_status == ClaimVerificationStatus.MOCK for c in rule_claims)
    assert result.citation_coverage > 0


@pytest.mark.asyncio
async def test_engine_no_relevant_evidence_never_earns_high_confidence(db_session, indexed_dataset):
    """A keyword-empty query means PostgresKeywordRetriever contributes
    nothing; MockEmbeddingProvider is non-semantic (Phase 2 REAL/MOCK split),
    so the vector leg can still surface *some* deterministic-but-irrelevant
    chunk — this must never be enough to earn HIGH confidence.
    """
    request = LegalResearchRequest(question="совершенно нерелевантный вопрос без совпадений xyz999")
    result, _ = await _engine(db_session).run(request)

    assert result.confidence != ConfidenceLevel.HIGH


@pytest.mark.asyncio
async def test_engine_respects_effective_at_temporal_pin(db_session, indexed_dataset):
    request = LegalResearchRequest(
        question="надлежащим образом исполнение", effective_at=date(2024, 6, 1)
    )
    result, _ = await _engine(db_session).run(request)

    rule_claims = [c for c in result.claims if c.claim_type == "rule" and "309" in c.claim]
    # if ст.309 was cited, it must be the OLD redaction valid on 2024-06-01
    for claim in rule_claims:
        assert "обычаями делового оборота" not in claim.claim  # that phrase only exists in the 2025 redaction


@pytest.mark.asyncio
async def test_engine_trace_never_contains_chain_of_thought_field():
    """Structural guarantee — brief §37: ResearchTrace's dataclass fields are
    all either counts, ids, or already-public structured data.
    """
    import dataclasses

    from app.domains.legal_research.models import ResearchTrace

    field_names = {f.name for f in dataclasses.fields(ResearchTrace)}
    forbidden = {"chain_of_thought", "raw_llm_output", "internal_reasoning", "thinking"}
    assert not (field_names & forbidden)


@pytest.mark.asyncio
async def test_engine_populates_performance_metrics(db_session, indexed_dataset):
    request = LegalResearchRequest(question="надлежащим образом")
    _, trace = await _engine(db_session).run(request)

    assert "retrieval_ms" in trace.performance_ms
    assert "reasoning_ms" in trace.performance_ms
    assert "total_ms" in trace.performance_ms
    assert trace.llm_calls > 0


@pytest.mark.asyncio
async def test_engine_escalates_when_conflicting_practice_and_not_high_confidence(db_session, indexed_dataset):
    request = LegalResearchRequest(question="односторонний отказ от исполнения договора поставки")
    result, _ = await _engine(db_session).run(request)

    # This question retrieves both a "denied" and "partial"-outcome decision in
    # the mock KB (see app/sources/mock/dataset.py) -> conflicting practice.
    if any(c.conflict_type.value == "jurisprudential_conflict" for c in result.conflicts):
        assert result.confidence != ConfidenceLevel.HIGH or result.escalate_to_human


class _RaisingProvider:
    """Stands in for a real LLM provider hitting a hard failure (timeout,
    5xx, malformed response the SDK itself couldn't parse) — Phase 6.5
    brief §11/§12: an LLM failure must degrade to a controlled
    research_failed result, never a fabricated legal conclusion.
    """

    name = "raising"

    async def generate(self, *args, **kwargs):
        raise TimeoutError("simulated provider timeout")

    async def structured_generate(self, *args, **kwargs):
        raise TimeoutError("simulated provider timeout")


@pytest.mark.asyncio
async def test_engine_hard_llm_failure_never_fabricates_a_conclusion(db_session, indexed_dataset):
    request = LegalResearchRequest(question="надлежащим образом")
    engine = LegalResearchEngine(db_session, LLMGateway(provider=_RaisingProvider()))

    result, trace = await engine.run(request)

    assert result.status == "research_failed"
    assert result.executive_conclusion == ""
    assert result.escalate_to_human is True
    assert result.confidence == ConfidenceLevel.LOW
    assert result.citations == []
