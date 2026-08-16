"""Pydantic mirror of app.agents.base.LegalAgentResult — the structured-output
contract every AI-conclusion-bearing API response uses (LEGAL-AGENTS.md §7).
"""
from __future__ import annotations

from pydantic import BaseModel


class LegalIssueSchema(BaseModel):
    description: str
    article_refs: list[str] = []


class RiskSchema(BaseModel):
    severity: str
    description: str
    mitigation: str | None = None


class SourceSchema(BaseModel):
    citation_id: str | None
    verification_status: str


class LegalAgentResultSchema(BaseModel):
    conclusion: str
    confidence: str
    issues: list[LegalIssueSchema] = []
    risks: list[RiskSchema] = []
    sources: list[SourceSchema] = []
    citations: list[str] = []
    missing_facts: list[str] = []
    recommended_actions: list[str] = []
    escalate_to_human: bool = False
