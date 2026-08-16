"""Legal Reviewer Agent (LEGAL-AGENTS.md §4-5) — independent second opinion on any
Contract/Document Agent output (two-lawyer principle). Scaffold stage: the
critical structural rule already holds even in the stub — it only ever
receives a draft artifact, never the drafting agent's conversation/context,
so it cannot inherit the drafter's framing once real reasoning is wired in.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class LegalReviewerAgent(LegalAgent):
    name = "legal-reviewer-agent"
    handled_task_types = {"review_document"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        draft_only = {k: v for k, v in task.payload.items() if k in ("document_id", "content")}
        return LegalAgentResult(
            conclusion="Legal Reviewer Agent scaffold — independent review pipeline not yet implemented (Phase 2).",
            confidence="low",
            missing_facts=[
                f"Review pipeline pending Phase 2 implementation (received draft keys: {list(draft_only)})."
            ],
        )
