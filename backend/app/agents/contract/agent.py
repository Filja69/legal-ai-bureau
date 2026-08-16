"""Contract Agent (LEGAL-AGENTS.md §4) — draft/edit contracts (NDA, services, supply,
lease, IT/SaaS, employment-adjacent). Scaffold stage — see research/agent.py for the pattern.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class ContractAgent(LegalAgent):
    name = "contract-agent"
    handled_task_types = {"generate_contract", "edit_contract"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Contract Agent scaffold — drafting pipeline not yet implemented (Phase 3).",
            confidence="low",
            missing_facts=["Contract generation pipeline pending Phase 3 implementation."],
        )
