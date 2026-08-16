"""Risk verification through the Legal Research Engine — brief §24-27.

A detector's finding is a hypothesis, not a legal conclusion. Any candidate
that names a `research_question` gets routed through the SAME
`LegalResearchEngine` built in Phase 3 — nothing about legal research is
reimplemented here. What comes back determines `verification_status`
(VERIFIED/MOCK/UNVERIFIED); a candidate is never marked "legal risk
confirmed" on a detector's say-so alone.

Critically (brief §27): this module only ever *verifies whether the law
says something*, never converts "bad clause" into "illegal clause" — that
distinction is enforced by never letting `classification` be upgraded to
ILLEGAL/UNENFORCEABLE here, regardless of what research finds. Our current
Knowledge Base (Phase 2 mock dataset) has no data that could honestly
support such an upgrade anyway.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contracts.risk_detection import RiskCandidate
from app.domains.legal_research.engine import LegalResearchEngine
from app.domains.legal_research.models import ConfidenceLevel, LegalResearchRequest
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import RiskVerificationStatus


@dataclass
class VerifiedRisk:
    candidate: RiskCandidate
    verification_status: RiskVerificationStatus
    legal_basis: str | None
    citations: list[str]
    confidence: str  # high|medium|low — mirrors research confidence when research ran, else "low"
    research_id: str | None
    has_conflicting_practice: bool


async def verify_risks(
    session: AsyncSession, llm_gateway: LLMGateway, candidates: list[RiskCandidate],
    jurisdiction: str = "RU", effective_at: date | None = None,
) -> list[VerifiedRisk]:
    engine = LegalResearchEngine(session, llm_gateway)
    verified: list[VerifiedRisk] = []

    for candidate in candidates:
        if not candidate.research_question:
            # Structural/commercial finding — no legal claim was made, so
            # there is nothing for Legal Research to confirm or deny.
            verified.append(
                VerifiedRisk(
                    candidate=candidate, verification_status=RiskVerificationStatus.UNVERIFIED,
                    legal_basis=None, citations=[], confidence="low", research_id=None, has_conflicting_practice=False,
                )
            )
            continue

        request = LegalResearchRequest(question=candidate.research_question, jurisdiction=jurisdiction, effective_at=effective_at)
        result, trace = await engine.run(request)

        # Only "rule" claims carry a citation whose verification_status reflects
        # an actual CitationValidator check (Phase 2). The "conclusion" claim's
        # status just means "internally consistent with its rule claims" —
        # VERIFIED there can still be built entirely out of MOCK rules, so using
        # it here would silently launder mock evidence into a "verified" risk.
        rule_claims = [c for c in result.claims if c.claim_type == "rule"]
        mock_citations = [c.citations for c in rule_claims if c.verification_status.value == "mock"]
        verified_citations = [c.citations for c in rule_claims if c.verification_status.value == "verified"]
        has_any_citation = bool(mock_citations or verified_citations)

        if verified_citations:
            status = RiskVerificationStatus.VERIFIED
        elif mock_citations:
            status = RiskVerificationStatus.MOCK
        else:
            status = RiskVerificationStatus.UNVERIFIED

        verified.append(
            VerifiedRisk(
                candidate=candidate,
                verification_status=status,
                legal_basis=result.executive_conclusion if has_any_citation else None,
                citations=result.citations,
                confidence=result.confidence.value if isinstance(result.confidence, ConfidenceLevel) else str(result.confidence),
                research_id=trace.research_id,
                has_conflicting_practice=bool(result.conflicts),
            )
        )

    return verified
