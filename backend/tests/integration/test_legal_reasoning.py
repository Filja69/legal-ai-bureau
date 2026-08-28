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


# --- Case-law claims (P2) ---


@pytest.mark.asyncio
async def test_reasoner_produces_verified_case_law_claim_for_a_real_decision(db_session):
    """A retrieved court-decision chunk must be independently re-verified
    against the Knowledge Base (case_number resolution + source trust) the
    same way a statute citation is — never trusted from retrieval alone.
    """
    from app.models.case_law import Court, CourtDecision, CourtLevel
    from app.models.legal_knowledge import LegalDocument, LegalDocumentType

    source = LegalSource(name="Official Court DB", type=SourceType.COURT, is_official=True)
    db_session.add(source)
    await db_session.flush()
    court = Court(name="АС г. Москвы", level=CourtLevel.FIRST_INSTANCE, jurisdiction="RU")
    db_session.add(court)
    await db_session.flush()
    document = LegalDocument(
        title="Решение по делу А40-5555/2024", document_type=LegalDocumentType.COURT_DECISION,
        source_id=source.id, content="Суд отклонил довод о преждевременности требования.",
    )
    db_session.add(document)
    await db_session.flush()
    decision = CourtDecision(
        document_id=document.id, court_id=court.id, case_number="А40-5555/2024", decision_date="2024-01-01",
        claim_summary="Иск о взыскании долга.", decision_summary="Иск удовлетворен.",
        legal_reasoning="Суд отклонил довод о преждевременности требования.", outcome="granted",
    )
    db_session.add(decision)
    await db_session.flush()

    from app.domains.legal_research.models import EvidenceItem

    case_law_item = EvidenceItem(
        source=str(source.id), citation="А40-5555/2024", text="Суд отклонил довод о преждевременности требования.",
        retrieval_score=1.0, retrieval_method=["exact"],
        metadata={"chunk_type": "court_decision", "court_decision_id": str(decision.id), "case_number": "А40-5555/2024"},
    )

    issue = LegalIssue(id="1", title="Преждевременность требования", description="d", priority=1)
    reasoner = LegalReasoner(db_session, LLMGateway(provider=MockLLMProvider()))
    claims, _ = await reasoner.reason(issue, [case_law_item], facts=[], effective_at=None)

    case_law_claims = [c for c in claims if c.claim_type == "case_law"]
    assert len(case_law_claims) == 1
    assert case_law_claims[0].verification_status == ClaimVerificationStatus.VERIFIED
    assert case_law_claims[0].citations == ["А40-5555/2024"]


@pytest.mark.asyncio
async def test_reasoner_never_cites_a_fabricated_case_number(db_session):
    """A case number that resolves to nothing in the Knowledge Base — the
    LLM inventing a plausible-looking citation — must never be trusted."""
    from app.domains.legal_research.models import EvidenceItem

    fabricated = EvidenceItem(
        source="s", citation="А99-9999/2099", text="fabricated reasoning", retrieval_score=1.0,
        retrieval_method=["exact"], metadata={"chunk_type": "court_decision", "case_number": "А99-9999/2099"},
    )
    issue = LegalIssue(id="1", title="issue", description="d", priority=1)
    reasoner = LegalReasoner(db_session, LLMGateway(provider=MockLLMProvider()))
    claims, _ = await reasoner.reason(issue, [fabricated], facts=[], effective_at=None)

    case_law_claims = [c for c in claims if c.claim_type == "case_law"]
    assert case_law_claims[0].verification_status == ClaimVerificationStatus.UNVERIFIED
    assert case_law_claims[0].citations == []
