from __future__ import annotations

import pytest

from app.domains.legal_research.issue_identification import IssueIdentifier, ResearchPlanner
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway


@pytest.mark.asyncio
async def test_issue_identification_falls_back_to_question_under_mock_llm():
    identifier = IssueIdentifier(LLMGateway(provider=MockLLMProvider()))
    issues = await identifier.identify("Может ли заказчик отказаться от договора?", [])

    assert len(issues) == 1
    assert issues[0].priority == 1
    assert "заказчик" in issues[0].title


@pytest.mark.asyncio
async def test_issues_are_sorted_by_priority():
    identifier = IssueIdentifier(LLMGateway(provider=MockLLMProvider()))
    issues = await identifier.identify("q", [])
    priorities = [i.priority for i in issues]
    assert priorities == sorted(priorities)


def test_research_planner_builds_plan_with_issues_and_domain():
    from app.domains.legal_research.models import LegalIssue

    planner = ResearchPlanner()
    issue = LegalIssue(id="1", title="t", description="d", priority=1)
    plan = planner.build_plan([issue], jurisdiction="RU", effective_at=None)

    assert plan.issues == [issue]
    assert "RU" in plan.legal_domains
    assert "applicable_law" in plan.required_evidence
