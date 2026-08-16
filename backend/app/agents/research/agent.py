"""Research Agent (LEGAL-AGENTS.md §4) — norms, case law, regulatory acts, court positions.

Scaffold stage: implements the LegalAgent Protocol and wires through the
LLMGateway + retrieval interfaces, but the reasoning pipeline
(LEGAL-AGENTS.md §2) is not yet assembled — `run` returns a low-confidence
placeholder result rather than a real legal conclusion. Real implementation
lands in Phase 2 (Core Engine).
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class ResearchAgent(LegalAgent):
    name = "research-agent"
    handled_task_types = {"legal_research"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Research Agent scaffold — reasoning pipeline not yet implemented (Phase 2).",
            confidence="low",
            missing_facts=["Full reasoning pipeline pending Phase 2 implementation."],
            escalate_to_human=False,
        )
