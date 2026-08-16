"""Due Diligence Agent (LEGAL-AGENTS.md §4) — counterparty/company legal risk profile.
Scaffold stage — see research/agent.py for the pattern.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class DueDiligenceAgent(LegalAgent):
    name = "due-diligence-agent"
    handled_task_types = {"due_diligence"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Due Diligence Agent scaffold — DD module not yet implemented (Phase 5).",
            confidence="low",
            missing_facts=["Due diligence module pending Phase 5 implementation."],
        )
