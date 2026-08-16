"""Phase 4 contract evaluation dataset — brief §55-57. 40 deterministic
cases: 10 obvious risks, 10 subtle risks, 5 missing clauses, 5 one-sided
clauses, 5 temporal/legal issues, 5 adversarial (hallucination-resistance).

Adversarial cases are load-bearing (brief §56-57): the specific fabricated
article/case number named in each case must never be verified/mock-cited
against the Knowledge Base, regardless of contract framing.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.domains.contracts.mock_contracts import MOCK_CONTRACTS
from app.domains.contracts.risk_detection import RiskCandidate, run_all_detectors
from app.domains.contracts.risk_verification import verify_risks
from app.domains.contracts.severity import SeverityInputs
from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import ContractType, RiskCategory, RiskClassification, RiskType, RiskVerificationStatus
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource

_CASES_DIR = Path(__file__).parent
_CASES = sorted(_CASES_DIR.glob("case_*.json"))
_MOCK_CONTRACTS_BY_KEY = {r["key"]: r for r in MOCK_CONTRACTS}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


_CLAUSE_CASE_CATEGORIES = {"obvious_risk", "subtle_risk", "missing_clause", "one_sided_clause"}


@pytest.mark.parametrize("case_path", [p for p in _CASES if _load(p)["category"] in _CLAUSE_CASE_CATEGORIES], ids=lambda p: p.stem)
def test_contract_eval_case_detects_expected_risk(case_path):
    case = _load(case_path)

    if case["contract_key"]:
        record = _MOCK_CONTRACTS_BY_KEY[case["contract_key"]]
        text = record["text"]
        contract_type = ContractType(record["contract_type"])
    else:
        text = case["custom_text"]
        try:
            contract_type = ContractType(case["contract_type"])
        except ValueError:
            contract_type = ContractType.OTHER

    clauses = ContractStructureExtractor().extract(text)
    candidates = run_all_detectors(clauses, contract_type)
    found_types = {c.risk_type.value for c in candidates}

    missing = set(case["expected_risk_types"]) - found_types
    assert not missing, f"{case['case_id']}: expected risk types {missing} not found; got {found_types}"


@pytest.mark.asyncio
@pytest.mark.parametrize("case_path", [p for p in _CASES if _load(p)["category"] == "temporal_legal"], ids=lambda p: p.stem)
async def test_contract_eval_case_temporal_legal_research(db_session, indexed_dataset, case_path):
    case = _load(case_path)
    effective_at = date.fromisoformat(case["effective_at"]) if case.get("effective_at") else None

    candidate = RiskCandidate(
        detector="liability", risk_type=RiskType.UNLIMITED_LIABILITY, category=RiskCategory.LEGAL,
        classification=RiskClassification.HIGH_RISK, title="t", description="d", why_it_matters="w",
        severity_inputs=SeverityInputs(50, 50, 50, 50, 50), clause_index=0, research_question=case["research_question"],
    )

    results = await verify_risks(
        db_session, LLMGateway(provider=MockLLMProvider()), [candidate], jurisdiction="RU", effective_at=effective_at
    )
    result = results[0]

    if result.verification_status in (RiskVerificationStatus.VERIFIED, RiskVerificationStatus.MOCK):
        assert any(exp in c for exp in case["expected_citations_any"] for c in result.citations), (
            f"{case['case_id']}: citations {result.citations} do not contain any of {case['expected_citations_any']}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("case_path", [p for p in _CASES if _load(p)["category"] == "adversarial"], ids=lambda p: p.stem)
async def test_contract_eval_case_never_hallucinates(db_session, indexed_dataset, case_path):
    case = _load(case_path)
    effective_at = date.fromisoformat(case["effective_at"]) if case.get("effective_at") else None

    candidate = RiskCandidate(
        detector="liability", risk_type=RiskType.UNLIMITED_LIABILITY, category=RiskCategory.LEGAL,
        classification=RiskClassification.HIGH_RISK, title="t", description="d", why_it_matters="w",
        severity_inputs=SeverityInputs(50, 50, 50, 50, 50), clause_index=0, research_question=case["research_question"],
    )

    results = await verify_risks(
        db_session, LLMGateway(provider=MockLLMProvider()), [candidate], jurisdiction="RU", effective_at=effective_at
    )
    result = results[0]

    for forbidden_article in case.get("must_not_claim_articles", []):
        assert not any(forbidden_article in c for c in result.citations), (
            f"{case['case_id']}: forbidden article {forbidden_article} appeared in citations {result.citations}"
        )
        assert result.verification_status != RiskVerificationStatus.VERIFIED or forbidden_article not in (result.legal_basis or "")

    for forbidden_case in case.get("must_not_claim_case_numbers", []):
        assert forbidden_case not in (result.legal_basis or ""), f"{case['case_id']}: forbidden case number claimed"


def test_contract_eval_dataset_has_at_least_40_cases():
    assert len(_CASES) >= 40


def test_contract_eval_dataset_covers_all_categories():
    categories = {_load(p)["category"] for p in _CASES}
    assert categories == {"obvious_risk", "subtle_risk", "missing_clause", "one_sided_clause", "temporal_legal", "adversarial"}


def test_contract_eval_dataset_has_at_least_5_adversarial_cases():
    adversarial = [p for p in _CASES if _load(p)["category"] == "adversarial"]
    assert len(adversarial) >= 5
