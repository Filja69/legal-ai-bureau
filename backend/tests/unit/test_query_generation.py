from __future__ import annotations

import pytest

from app.domains.legal_research.models import LegalIssue, QueryType
from app.domains.legal_research.query_generation import LegalQueryGenerator
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway


@pytest.mark.asyncio
async def test_query_generation_falls_back_to_issue_title_under_mock_llm():
    generator = LegalQueryGenerator(LLMGateway(provider=MockLLMProvider()))
    issue = LegalIssue(id="1", title="Право на односторонний отказ", description="d", priority=1)

    queries = await generator.generate(issue)

    assert len(queries) == 1
    assert queries[0].text == issue.title
    assert queries[0].query_type == QueryType.LAW
    assert queries[0].issue_id == "1"
