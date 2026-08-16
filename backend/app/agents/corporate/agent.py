"""Corporate Agent (LEGAL-AGENTS.md §4) — ООО/АО, participants, directors, protocols,
corporate transactions, interested-party deals. Scaffold stage — see research/agent.py.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class CorporateAgent(LegalAgent):
    name = "corporate-agent"
    handled_task_types = {"corporate_document", "corporate_event"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Corporate Agent scaffold — corporate module not yet implemented (Phase 5).",
            confidence="low",
            missing_facts=["Corporate law module pending Phase 5 implementation."],
        )
