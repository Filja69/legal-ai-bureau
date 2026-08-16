"""Compliance Agent (LEGAL-AGENTS.md §4) — regulatory/internal-policy conformance.
Scaffold stage — see research/agent.py for the pattern.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class ComplianceAgent(LegalAgent):
    name = "compliance-agent"
    handled_task_types = {"compliance_check"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Compliance Agent scaffold — not yet implemented.",
            confidence="low",
            missing_facts=["Compliance checking pending future phase implementation."],
        )
