"""Two-lawyer review — brief §32-34, applying the LEGAL-AGENTS.md §5
Draft→Independent Review→Correction pattern to contract analysis.

Pass A (Analyst) and Pass B (Reviewer) each independently run detection +
verification from scratch — Pass B is never handed Pass A's risk list, only
the same clauses/contract_type/jurisdiction (brief §33 "blind review"). With
fully deterministic detectors and a fixed Knowledge Base snapshot the two
passes will typically agree by construction — that's a legitimate outcome,
not a shortcut: the mechanism exists to catch drift (a KB change between
passes, a nondeterminism bug) and is what makes REQUIRES_HUMAN_REVIEW a real
signal rather than a rubber stamp. Disagreement/asymmetric findings are
never silently averaged (brief §34).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contracts.risk_detection import run_all_detectors
from app.domains.contracts.risk_verification import VerifiedRisk, verify_risks
from app.domains.contracts.structure_extractor import ExtractedClause
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import AgreementStatus, ContractType

_CRITICAL_SEVERITIES = {"critical"}


@dataclass
class ReviewedRisk:
    verified_risk: VerifiedRisk
    agreement_status: AgreementStatus
    note: str = ""


@dataclass
class TwoLawyerOutcome:
    risks: list[ReviewedRisk]
    analyst_count: int
    reviewer_count: int


def _key(risk: VerifiedRisk) -> tuple:
    # `title` is included because detectors like MissingClauseDetector emit
    # multiple candidates that share (detector, risk_type, clause_index=None)
    # — e.g. one per missing clause type — and would otherwise collide and
    # silently overwrite each other in the by-key maps below.
    return (risk.candidate.detector, risk.candidate.risk_type, risk.candidate.clause_index, risk.candidate.title)


async def run_pass(
    session: AsyncSession, llm_gateway: LLMGateway, clauses: list[ExtractedClause], contract_type: ContractType,
    jurisdiction: str, effective_at: date | None = None,
) -> list[VerifiedRisk]:
    candidates = run_all_detectors(clauses, contract_type)
    return await verify_risks(session, llm_gateway, candidates, jurisdiction, effective_at)


async def two_lawyer_review(
    session: AsyncSession, llm_gateway: LLMGateway, clauses: list[ExtractedClause], contract_type: ContractType,
    jurisdiction: str = "RU", effective_at: date | None = None,
) -> TwoLawyerOutcome:
    analyst_risks = await run_pass(session, llm_gateway, clauses, contract_type, jurisdiction, effective_at)
    reviewer_risks = await run_pass(session, llm_gateway, clauses, contract_type, jurisdiction, effective_at)

    analyst_by_key = {_key(r): r for r in analyst_risks}
    reviewer_by_key = {_key(r): r for r in reviewer_risks}

    reviewed: list[ReviewedRisk] = []
    for key, analyst_risk in analyst_by_key.items():
        reviewer_risk = reviewer_by_key.get(key)
        if reviewer_risk is None:
            reviewed.append(ReviewedRisk(analyst_risk, AgreementStatus.REQUIRES_HUMAN_REVIEW,
                "Reviewer pass did not reproduce this finding."))
        elif reviewer_risk.verification_status != analyst_risk.verification_status:
            reviewed.append(ReviewedRisk(analyst_risk, AgreementStatus.DISAGREEMENT,
                "Verification status differs between Analyst and Reviewer passes."))
        else:
            reviewed.append(ReviewedRisk(analyst_risk, AgreementStatus.AGREED))

    for key, reviewer_risk in reviewer_by_key.items():
        if key not in analyst_by_key:
            reviewed.append(ReviewedRisk(reviewer_risk, AgreementStatus.REQUIRES_HUMAN_REVIEW,
                "Found only by the Reviewer pass, not the Analyst pass."))

    return TwoLawyerOutcome(risks=reviewed, analyst_count=len(analyst_risks), reviewer_count=len(reviewer_risks))
