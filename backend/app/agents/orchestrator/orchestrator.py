"""Legal Orchestrator (LEGAL-AGENTS.md §8) — routes tasks to specialist agents and
merges their structured results. The only component allowed to assemble a
FINAL ANSWER. Scaffold stage: routing table + merge shape are real; the
full reasoning pipeline (LEGAL-AGENTS.md §2) is Phase 2 work.
"""
from __future__ import annotations

from app.agents.base import AgentTask, LegalAgent, LegalAgentResult
from app.core.exceptions import NotFoundError


class LegalOrchestrator:
    def __init__(self, agents: list[LegalAgent]) -> None:
        self._agents = agents

    async def dispatch(self, task: AgentTask) -> LegalAgentResult:
        for agent in self._agents:
            if await agent.can_handle(task):
                result = await agent.run(task)
                return self._apply_escalation_rules(result)
        raise NotFoundError(f"No registered agent can handle task_type={task.task_type!r}")

    @staticmethod
    def _apply_escalation_rules(result: LegalAgentResult) -> LegalAgentResult:
        """PRD §9 escalation triggers — critical severity or unverified
        load-bearing citations force escalate_to_human, regardless of what
        the originating agent set.
        """
        if any(risk.severity == "critical" for risk in result.risks):
            result.escalate_to_human = True
        if any(src.verification_status == "unverified" for src in result.sources) and result.confidence != "low":
            result.confidence = "low"
        return result
