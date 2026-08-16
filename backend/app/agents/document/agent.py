"""Legal Document Agent (LEGAL-AGENTS.md §4) — generic document generation (letters,
claims, notices) not owned by a more specific agent. Scaffold stage.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.llm.routing.gateway import LLMGateway


class LegalDocumentAgent(LegalAgent):
    name = "legal-document-agent"
    handled_task_types = {"generate_document"}

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self._llm = llm_gateway

    async def can_handle(self, task: AgentTask) -> bool:
        return task.task_type in self.handled_task_types

    async def run(self, task: AgentTask) -> LegalAgentResult:
        return LegalAgentResult(
            conclusion="Legal Document Agent scaffold — generation pipeline not yet implemented (Phase 3).",
            confidence="low",
            missing_facts=["Document generation pending Phase 3 implementation."],
        )
