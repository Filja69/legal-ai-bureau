"""Legal Risk Agent (LEGAL-AGENTS.md §4) — aggregates RiskItems across a
case/contract/company into a Risk Matrix. Reads DB, no external tools.
Scaffold stage.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class LegalRiskAgent(LegalAgent):
    name = "legal-risk-agent"
    handled_task_types = {"risk_matrix"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Legal Risk Agent scaffold — risk aggregation not yet implemented (Phase 2).",
            confidence="low",
            missing_facts=["Risk matrix aggregation pending Phase 2 implementation."],
        )
