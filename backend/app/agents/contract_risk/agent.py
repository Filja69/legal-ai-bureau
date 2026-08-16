"""Contract Risk Agent (LEGAL-AGENTS.md §4) — clause-level risk: penalties, unilateral
changes, auto-renewal, liability, jurisdiction, IP/payment/termination risk.
Scaffold stage — see research/agent.py for the pattern.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class ContractRiskAgent(LegalAgent):
    name = "contract-risk-agent"
    handled_task_types = {"analyze_contract_risk"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Contract Risk Agent scaffold — risk detection not yet implemented (Phase 3).",
            confidence="low",
            missing_facts=["Clause-level risk scoring pending Phase 3 implementation."],
        )
