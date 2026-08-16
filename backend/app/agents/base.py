"""LegalAgent Protocol + LegalAgentResult (LEGAL-AGENTS.md §4, §7).

Every specialized agent implements this Protocol. The Orchestrator
(app/agents/orchestrator/) is the only component allowed to assemble a
final user-facing answer out of one or more LegalAgentResult objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AgentTask:
    """What the Orchestrator hands to a specialized agent."""

    task_type: str
    workspace_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    case_id: str | None = None
    event_date: str | None = None


@dataclass
class LegalIssueRef:
    description: str
    article_refs: list[str] = field(default_factory=list)


@dataclass
class RiskRef:
    severity: str  # low|medium|high|critical
    description: str
    mitigation: str | None = None


@dataclass
class SourceRef:
    citation_id: str | None
    verification_status: str  # verified|unverified|broken


@dataclass
class LegalAgentResult:
    """Structured output contract — LEGAL-AGENTS.md §7. Agents never return bare text."""

    conclusion: str
    confidence: str  # high|medium|low
    issues: list[LegalIssueRef] = field(default_factory=list)
    risks: list[RiskRef] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    escalate_to_human: bool = False


class LegalAgent(Protocol):
    """Base contract every specialized agent implements."""

    name: str

    async def can_handle(self, task: AgentTask) -> bool: ...

    async def run(self, task: AgentTask) -> LegalAgentResult: ...
