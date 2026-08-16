"""LegalReasoner — brief §16-20. IRAC internally, claim-to-citation mapping
re-verified independently rather than trusted from retrieval alone.
"""
from __future__ import annotations

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.domains.legal_research.evidence_ranking import EvidenceRanker
from app.domains.legal_research.models import ClaimVerificationStatus, LegalIssue, QueryType, ResearchQuery
from app.domains.legal_research.reasoning import LegalReasoner
from app.domains.legal_research.retrieval_pipeline import MultiStageRetriever
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


@pytest.mark.asyncio
async def test_reasoner_produces_mock_verified_rule_claims(db_session, indexed_dataset):
    issue = LegalIssue(id="1", title="Право на отказ", description="d", priority=1)
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[],
    )
    ranked = await EvidenceRanker(db_session).rank(pool)

    reasoner = LegalReasoner(db_session, LLMGateway(provider=MockLLMProvider()))
    claims, application = await reasoner.reason(issue, ranked.items, facts=["заказчик уведомил исполнителя"], effective_at=None)

    rule_claims = [c for c in claims if c.claim_type == "rule"]
    assert len(rule_claims) >= 1
    assert all(c.verification_status == ClaimVerificationStatus.MOCK for c in rule_claims)
    assert all(c.citations for c in rule_claims)


@pytest.mark.asyncio
async def test_reasoner_conclusion_claim_present_and_typed(db_session, indexed_dataset):
    issue = LegalIssue(id="1", title="Право на отказ", description="d", priority=1)
    retriever = MultiStageRetriever(db_session)
    pool = await retriever.run(
        [ResearchQuery(text="надлежащим образом", query_type=QueryType.LAW, issue_id="1")],
        jurisdiction="RU", effective_at=None, facts=[],
    )
    ranked = await EvidenceRanker(db_session).rank(pool)

    reasoner = LegalReasoner(db_session, LLMGateway(provider=MockLLMProvider()))
    claims, _ = await reasoner.reason(issue, ranked.items, facts=[], effective_at=None)

    conclusions = [c for c in claims if c.claim_type == "conclusion"]
    assert len(conclusions) == 1
    assert conclusions[0].importance.value == "critical"


@pytest.mark.asyncio
async def test_reasoner_with_no_evidence_produces_no_rule_claims_and_honest_narrative(db_session, indexed_dataset):
    issue = LegalIssue(id="1", title="Совершенно нерелевантный вопрос xyz123", description="d", priority=1)

    reasoner = LegalReasoner(db_session, LLMGateway(provider=MockLLMProvider()))
    claims, application = await reasoner.reason(issue, [], facts=[], effective_at=None)

    assert not [c for c in claims if c.claim_type == "rule"]
    assert "mock" in application.lower() or "недоступно" in application.lower()


@pytest.mark.asyncio
async def test_reasoner_never_cites_unverifiable_article(db_session, indexed_dataset):
    """Even if retrieval somehow surfaced a chunk for a nonexistent article,
    the reasoner's re-verification (not trust-the-retriever) must catch it.
    """
    from app.domains.legal_research.models import EvidenceItem

    issue = LegalIssue(id="1", title="issue", description="d", priority=1)
    fabricated = EvidenceItem(
        source="s", citation="ст. 99999", text="fabricated text", retrieval_score=1.0,
        retrieval_method=["exact"], metadata={"chunk_type": "law_version", "article_number": "99999", "law_id": None},
    )

    reasoner = LegalReasoner(db_session, LLMGateway(provider=MockLLMProvider()))
    claims, _ = await reasoner.reason(issue, [fabricated], facts=[], effective_at=None)

    rule_claims = [c for c in claims if c.claim_type == "rule"]
    assert rule_claims[0].verification_status == ClaimVerificationStatus.UNVERIFIED
    assert rule_claims[0].citations == []
