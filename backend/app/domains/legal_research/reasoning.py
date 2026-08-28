"""LegalReasoner — brief §16-20, IRAC structure (Issue/Rule/Application/
Conclusion) used internally, not forced as a literal template on every answer.

Every RULE claim is citation-backed and independently re-verified through
the existing CitationValidator (Phase 2) before it's trusted — the reasoner
never marks its own citations correct. APPLICATION/CONCLUSION narratives
come from LLMGateway (TaskClass.REASONING); under LLM_PROVIDER=mock these
are honestly empty, and the reasoner falls back to a plain statement that no
AI narrative is available rather than inventing one.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_research.models import (
    ClaimImportance,
    ClaimVerificationStatus,
    EvidenceItem,
    LegalClaim,
    LegalIssue,
)
from app.llm.base import LLMMessage
from app.llm.prompt_safety import UNTRUSTED_CONTENT_NOTICE, wrap_untrusted
from app.llm.routing.gateway import LLMGateway, TaskClass
from app.models.legal_knowledge import Law
from app.rag.validation.citation_validator import CitationDraft, CitationStatus, CitationValidator

_APPLICATION_SCHEMA = {
    "type": "object",
    "properties": {"application": {"type": "string"}, "conclusion": {"type": "string"}},
}

_SYSTEM_PROMPT = (
    "You apply cited Russian legal rules to the given facts for one legal issue. Use only "
    "the rules and facts provided — never introduce a fact or a citation that wasn't given "
    "to you. State the conclusion as direct, qualified, or conditional as the evidence "
    "actually supports; never overstate certainty. Respond via the schema.\n\n" + UNTRUSTED_CONTENT_NOTICE
)

_NO_AI_NARRATIVE = "Автоматическое юридическое заключение недоступно (LLM в mock-режиме) — см. процитированные источники."

_CITATION_STATUS_TO_CLAIM_STATUS = {
    CitationStatus.VERIFIED: ClaimVerificationStatus.VERIFIED,
    CitationStatus.MOCK: ClaimVerificationStatus.MOCK,
    CitationStatus.UNVERIFIED: ClaimVerificationStatus.UNVERIFIED,
    CitationStatus.BROKEN: ClaimVerificationStatus.UNVERIFIED,
    CitationStatus.TEMPORALLY_INVALID: ClaimVerificationStatus.UNVERIFIED,
}


class LegalReasoner:
    def __init__(self, session: AsyncSession, llm_gateway: LLMGateway) -> None:
        self._session = session
        self._llm = llm_gateway
        self._validator = CitationValidator(session)

    async def reason(
        self, issue: LegalIssue, evidence: list[EvidenceItem], facts: list[str], effective_at
    ) -> tuple[list[LegalClaim], str]:
        """Returns (claims, application_narrative) for one issue."""
        rule_claims = await self._build_rule_claims(issue, evidence, effective_at)

        narrative = await self._apply(issue, rule_claims, facts)

        # Status here reflects only the rule claims' own verification — the
        # UNSUPPORTED_CRITICAL escalation (brief §25) is applied uniformly to
        # every claim by LegalResearchReviewer, not decided ad hoc per claim type.
        rule_claims_ok = (ClaimVerificationStatus.VERIFIED, ClaimVerificationStatus.MOCK)
        if rule_claims and all(c.verification_status in rule_claims_ok for c in rule_claims):
            conclusion_status = ClaimVerificationStatus.VERIFIED
        else:
            conclusion_status = ClaimVerificationStatus.UNVERIFIED

        conclusion_claim = LegalClaim(
            claim=narrative["conclusion"] or _NO_AI_NARRATIVE,
            claim_type="conclusion",
            importance=ClaimImportance.CRITICAL if issue.priority == 1 else ClaimImportance.IMPORTANT,
            citations=[cit for c in rule_claims for cit in c.citations],
            verification_status=conclusion_status,
            issue_id=issue.id,
        )

        return [*rule_claims, conclusion_claim], narrative["application"] or _NO_AI_NARRATIVE

    async def _build_rule_claims(self, issue: LegalIssue, evidence: list[EvidenceItem], effective_at) -> list[LegalClaim]:
        law_items = [e for e in evidence if e.metadata.get("chunk_type") == "law_version"]
        case_law_items = [e for e in evidence if e.metadata.get("chunk_type") == "court_decision"]
        importance = ClaimImportance.CRITICAL if issue.priority == 1 else ClaimImportance.IMPORTANT
        claims: list[LegalClaim] = []

        for item in law_items:
            law_short_name = await self._resolve_law_short_name(item.metadata.get("law_id"))
            article_number = item.metadata.get("article_number")

            check = await self._validator.validate(
                CitationDraft(law_short_name=law_short_name, article_number=article_number, quoted_fragment=None, event_date=effective_at)
            )

            claims.append(
                LegalClaim(
                    claim=f"{item.citation}: {item.text}",
                    claim_type="rule",
                    importance=importance,
                    citations=[item.citation] if check.status != CitationStatus.UNVERIFIED else [],
                    verification_status=_CITATION_STATUS_TO_CLAIM_STATUS.get(check.status, ClaimVerificationStatus.UNVERIFIED),
                    issue_id=issue.id,
                )
            )

        # Retrieved case law was previously ranked (EvidenceRanker) but never
        # actually cited or verified — a real gap: it could inform a
        # narrative without ever being independently confirmed to exist.
        # Every case-law item is now validated the same way a statute
        # citation is (case_number resolution + source trust), before it can
        # support any conclusion.
        for item in case_law_items:
            case_number = item.metadata.get("case_number")
            check = await self._validator.validate_case_law(
                CitationDraft(law_short_name=None, article_number=None, quoted_fragment=None, case_number=case_number)
            )
            claims.append(
                LegalClaim(
                    claim=f"{item.citation}: {item.text}",
                    claim_type="case_law",
                    importance=importance,
                    citations=[item.citation] if check.status != CitationStatus.UNVERIFIED else [],
                    verification_status=_CITATION_STATUS_TO_CLAIM_STATUS.get(check.status, ClaimVerificationStatus.UNVERIFIED),
                    issue_id=issue.id,
                )
            )
        return claims

    async def _resolve_law_short_name(self, law_id: str | None) -> str | None:
        if not law_id:
            return None
        result = await self._session.execute(select(Law.short_name).where(Law.id == law_id))
        return result.scalars().first()

    async def _apply(self, issue: LegalIssue, rule_claims: list[LegalClaim], facts: list[str]) -> dict:
        rules_text = "\n".join(c.claim for c in rule_claims) or "(no verified rules found)"
        prompt = (
            f"{wrap_untrusted('issue', issue.title)}\n"
            f"{wrap_untrusted('facts', str(facts) if facts else '(none stated)')}\n"
            f"{wrap_untrusted('retrieved_rules', rules_text)}"
        )
        raw = await self._llm.structured_generate(
            TaskClass.REASONING,
            [LLMMessage(role="user", content=prompt)],
            response_schema=_APPLICATION_SCHEMA,
            system=_SYSTEM_PROMPT,
        )
        return raw or {"application": "", "conclusion": ""}
