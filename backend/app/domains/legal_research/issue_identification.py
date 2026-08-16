"""IssueIdentifier + ResearchPlanner — brief §7-8.

Issue identification is LLM-driven (TaskClass.CLASSIFICATION — cheap/fast
model, matching LEGAL-ARCHITECTURE.md §4's task-class routing). Under
LLM_PROVIDER=mock this returns no issues; rather than let the pipeline
dead-end with zero issues (and therefore zero research), a single
structural fallback issue is derived from the raw question — it carries no
invented legal content, just "this question, as stated, is the issue."
"""
from __future__ import annotations

import uuid

from app.domains.legal_research.models import LegalIssue, ResearchPlan
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass

_ISSUES_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array"}},
}

_SYSTEM_PROMPT = (
    "You identify the legal issues raised by a Russian-law question. Return a primary "
    "issue (priority=1) and any secondary issues (priority>=2) via the issues schema. "
    "Each issue needs a short title and one-sentence description.\n\n" + UNTRUSTED_CONTENT_NOTICE
)


class IssueIdentifier:
    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def identify(self, question: str, facts: list[str]) -> list[LegalIssue]:
        prompt = f"{wrap_untrusted('question', question)}\n{wrap_untrusted('facts', str(facts) if facts else '(none)')}"
        raw = await self._llm.structured_generate(
            TaskClass.CLASSIFICATION,
            [LLMMessage(role="user", content=prompt)],
            response_schema=_ISSUES_SCHEMA,
            system=_SYSTEM_PROMPT,
        )
        entries = (raw or {}).get("issues") or []

        issues: list[LegalIssue] = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("title"):
                continue
            issues.append(
                LegalIssue(
                    id=str(uuid.uuid4()),
                    title=entry["title"],
                    description=entry.get("description", ""),
                    priority=int(entry.get("priority", 2)),
                    parent_issue=entry.get("parent_issue"),
                )
            )

        if not issues:
            issues.append(
                LegalIssue(id=str(uuid.uuid4()), title=question.strip()[:200], description=question, priority=1)
            )
        return sorted(issues, key=lambda i: i.priority)


class ResearchPlanner:
    def build_plan(self, issues: list[LegalIssue], jurisdiction: str, effective_at) -> ResearchPlan:
        return ResearchPlan(
            issues=issues,
            date_constraint=effective_at,
            legal_domains=[jurisdiction],
            required_evidence=["applicable_law", "court_practice"],
        )
