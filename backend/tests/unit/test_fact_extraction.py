from __future__ import annotations

import pytest

from app.domains.legal_research.fact_extraction import FactExtractor
from app.domains.legal_research.models import FactOrigin
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway


@pytest.mark.asyncio
async def test_user_facts_are_trusted_as_user_stated():
    extractor = FactExtractor(LLMGateway(provider=MockLLMProvider()))
    facts, _ = await extractor.extract("question", ["договор заключен между ООО и ИП", "услуги ежемесячно"])

    assert len(facts) == 2
    assert all(f.source == FactOrigin.USER_STATED for f in facts)
    assert all(f.confidence == 1.0 for f in facts)


@pytest.mark.asyncio
async def test_no_user_facts_returns_empty_list():
    extractor = FactExtractor(LLMGateway(provider=MockLLMProvider()))
    facts, _ = await extractor.extract("question", [])
    assert facts == []


@pytest.mark.asyncio
async def test_missing_facts_is_empty_under_mock_llm():
    """Honest degradation: mock LLM performs no real extraction, so missing_facts
    is empty rather than fabricated — LEGAL-RAG.md anti-hallucination principle
    applied to the research pipeline, not just citations.
    """
    extractor = FactExtractor(LLMGateway(provider=MockLLMProvider()))
    _, missing = await extractor.extract("Может ли заказчик отказаться от договора?", [])
    assert missing == []
