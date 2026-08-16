"""Litigation Agent (LEGAL-AGENTS.md §4) — claims, responses, motions, evidence, strategy.
Scaffold stage — see research/agent.py for the pattern.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class LitigationAgent(LegalAgent):
    name = "litigation-agent"
    handled_task_types = {"litigation_strategy", "draft_pleading"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Litigation Agent scaffold — strategy module not yet implemented (Phase 6).",
            confidence="low",
            missing_facts=["Litigation intelligence pending Phase 6 implementation."],
            escalate_to_human=True,  # litigation is a standing escalation trigger — PRD §9
        )
