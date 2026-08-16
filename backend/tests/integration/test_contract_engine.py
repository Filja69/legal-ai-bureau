"""ContractIntelligenceEngine — end-to-end pipeline + idempotency (brief §48)."""
from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

from app.domains.contracts.engine import ContractIntelligenceEngine
from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
from app.models.audit import AuditLog
from app.models.contracts import (
    Contract,
    ContractClause,
    ContractReviewStatus,
    ContractRisk,
    ContractType,
    ContractVersion,
    PartyPerspective,
    ReviewDepth,
)
from app.models.legal_knowledge import LegalSource, SourceType
from app.models.organization import Organization, Workspace
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource

_CONTRACT_TEXT = """1. Предмет договора

1.1. Исполнитель обязуется оказать услуги, а Заказчик обязуется принять и оплатить услуги.

2. Порядок оплаты

2.1. Заказчик осуществляет 100% предоплату до начала оказания услуг.

3. Ответственность сторон

3.1. Ответственность Исполнителя перед Заказчиком не ограничивается и наступает в полном объеме, включая косвенные убытки.

4. Расторжение

4.1. Заказчик вправе отказаться от исполнения договора в любое время без уведомления и без объяснения причин.
"""


@pytest.fixture
async def workspace(db_session):
    org = Organization(name="Org")
    db_session.add(org)
    await db_session.flush()
    ws = Workspace(organization_id=org.id, name="WS")
    db_session.add(ws)
    await db_session.flush()
    return org, ws


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


async def _make_contract_and_version(db_session, ws):
    contract = Contract(workspace_id=ws.id, title="Test Contract", contract_type=ContractType.SERVICE, is_mock=True)
    db_session.add(contract)
    await db_session.flush()
    content_hash = hashlib.sha256(_CONTRACT_TEXT.encode("utf-8")).hexdigest()
    version = ContractVersion(workspace_id=ws.id, contract_id=contract.id, version_number=1, content=_CONTRACT_TEXT,
        content_hash=content_hash)
    db_session.add(version)
    await db_session.flush()
    return contract, version


@pytest.mark.asyncio
async def test_engine_persists_clauses_risks_and_review(db_session, workspace, indexed_dataset):
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=MockLLMProvider()), org.id, ws.id)
    review = await engine.analyze(contract, version)
    await db_session.commit()

    assert review.status == ContractReviewStatus.COMPLETED
    assert review.overall_score < 100
    assert review.performance_ms["total_ms"] > 0

    clauses = (await db_session.execute(select(ContractClause).where(ContractClause.contract_id == contract.id))).scalars().all()
    assert len(clauses) > 0

    risks = (await db_session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))).scalars().all()
    assert len(risks) > 0
    assert any(r.risk_type.value == "unlimited_liability" for r in risks)
    assert any(r.risk_type.value == "one_sided_termination" for r in risks)


@pytest.mark.asyncio
async def test_engine_writes_audit_events(db_session, workspace, indexed_dataset):
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=MockLLMProvider()), org.id, ws.id)
    await engine.analyze(contract, version)
    await db_session.commit()

    events = (await db_session.execute(select(AuditLog).where(AuditLog.workspace_id == ws.id))).scalars().all()
    actions = {e.action for e in events}
    assert "CONTRACT_ANALYSIS_STARTED" in actions
    assert "CONTRACT_ANALYSIS_COMPLETED" in actions
    assert "RISK_CREATED" in actions


@pytest.mark.asyncio
async def test_engine_is_idempotent_for_same_configuration(db_session, workspace, indexed_dataset):
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=MockLLMProvider()), org.id, ws.id)
    first = await engine.analyze(contract, version)
    await db_session.commit()
    second = await engine.analyze(contract, version)
    await db_session.commit()

    assert first.id == second.id  # no duplicate review row created

    all_reviews = (await db_session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))).scalars().all()
    # risks from the first run only — re-analysis did not duplicate rows
    first_run_risk_count = len(all_reviews)
    third = await engine.analyze(contract, version)
    await db_session.commit()
    assert third.id == first.id
    after_third = (await db_session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))).scalars().all()
    assert len(after_third) == first_run_risk_count


@pytest.mark.asyncio
async def test_engine_force_reanalysis_creates_new_review(db_session, workspace, indexed_dataset):
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=MockLLMProvider()), org.id, ws.id)
    first = await engine.analyze(contract, version)
    await db_session.commit()
    second = await engine.analyze(contract, version, force=True)
    await db_session.commit()

    assert first.id != second.id


@pytest.mark.asyncio
async def test_engine_quick_depth_skips_verification(db_session, workspace, indexed_dataset):
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=MockLLMProvider()), org.id, ws.id)
    await engine.analyze(contract, version, review_depth=ReviewDepth.QUICK, force=True)
    await db_session.commit()

    risks = (await db_session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))).scalars().all()
    assert all(r.verification_status.value == "unverified" for r in risks)


@pytest.mark.asyncio
async def test_engine_stores_party_perspective_on_risks(db_session, workspace, indexed_dataset):
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=MockLLMProvider()), org.id, ws.id)
    await engine.analyze(contract, version, party_perspective=PartyPerspective.CUSTOMER)
    await db_session.commit()

    risks = (await db_session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))).scalars().all()
    assert all(r.party_perspective == PartyPerspective.CUSTOMER for r in risks)


class _RaisingProvider:
    """Simulated hard LLM failure (Phase 6.5 brief §11/§12) — a contract risk
    that needs Legal Research (UNLIMITED_LIABILITY/ONE_SIDED_TERMINATION both
    set research_question for this fixture's text) must never silently
    produce a risk report when the underlying research call fails.
    """

    name = "raising"

    async def generate(self, *args, **kwargs):
        raise TimeoutError("simulated provider timeout")

    async def structured_generate(self, *args, **kwargs):
        raise TimeoutError("simulated provider timeout")


@pytest.mark.asyncio
async def test_engine_hard_llm_failure_never_produces_a_fabricated_report(db_session, workspace, indexed_dataset):
    """A hard LLM/research failure while verifying a risk must never surface
    as a VERIFIED/MOCK citation — it degrades to UNVERIFIED, same as "no
    supporting research found" (LegalResearchEngine's own outer try/except
    already turns any exception into status="research_failed" rather than
    propagating — this test locks in that the contract layer honors that
    and never upgrades an unresearched claim to verified).
    """
    org, ws = workspace
    contract, version = await _make_contract_and_version(db_session, ws)

    engine = ContractIntelligenceEngine(db_session, LLMGateway(provider=_RaisingProvider()), org.id, ws.id)
    review = await engine.analyze(contract, version, force=True)
    await db_session.commit()

    assert review.status == ContractReviewStatus.COMPLETED
    risks = (await db_session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))).scalars().all()
    assert risks, "detectors still run deterministically even if research fails"
    for risk in risks:
        assert risk.verification_status.value in ("unverified", "mock")
        assert risk.citations in (None, [])
