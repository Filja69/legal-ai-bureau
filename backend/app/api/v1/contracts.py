"""Contract Intelligence — LEGAL-API.md §Contract Intelligence, Phase 4 revision.

Real end-to-end pipeline (app/domains/contracts/engine.py) wired to
persisted Contract/ContractVersion/ContractClause/ContractRisk/
ContractRecommendation/AlternativeClause/RedlineChange/ContractReview
tables. DOCX/PDF export (brief §64) is explicitly NOT implemented — real
501, not a fake 200.
"""
from __future__ import annotations

import hashlib
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_session
from app.domains.contracts.engine import ContractAnalysisFailedError, ContractIntelligenceEngine
from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.domains.contracts.version_diff import diff_clauses
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import (
    AlternativeClause,
    Contract,
    ContractClause,
    ContractRecommendation,
    ContractReview,
    ContractReviewStatus,
    ContractRisk,
    ContractVersion,
    RedlineChange,
    RedlineReviewStatus,
)
from app.models.matters import DocumentStatus
from app.models.organization import Workspace
from app.repositories.contract_repository import ContractRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.contract import AnalyzeRequest, ContractCreate, ContractOut
from app.security.deps import CurrentUser, get_current_user, get_workspace_id
from app.security.rate_limit import rate_limit_by_workspace

router = APIRouter(tags=["contracts"])
logger = structlog.get_logger(__name__)


async def _get_contract_or_404(session: AsyncSession, workspace_id: uuid.UUID, contract_id: uuid.UUID) -> Contract:
    contract = await ContractRepository(session, workspace_id).get(contract_id)
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found in this workspace")
    return contract


async def _get_current_version_or_404(session: AsyncSession, contract_id: uuid.UUID) -> ContractVersion:
    result = await session.execute(
        select(ContractVersion).where(ContractVersion.contract_id == contract_id, ContractVersion.is_current.is_(True))
    )
    version = result.scalars().first()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No version found for this contract")
    return version


async def _resolve_organization_id(session: AsyncSession, workspace_id: uuid.UUID) -> uuid.UUID:
    # Dev-mode CurrentUser (app/security/deps.py) fabricates a random,
    # unpersisted user/org identity — AuditLog.organization_id is a real,
    # NOT NULL foreign key, so it must come from the actual Workspace row
    # (which callers are required to create first), never from the auth stub.
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Workspace does not exist")
    return workspace.organization_id


@router.post("/contracts", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
async def create_contract(
    body: ContractCreate,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Contract:
    if body.raw_text is None and body.document_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Either raw_text or document_id must be provided")

    raw_text = body.raw_text
    if body.document_id is not None:
        # Phase 9.2 — real integration with Document Intelligence
        # (app/domains/documents/pipeline.py): Document Intelligence owns
        # FILE -> TEXT, Contract Intelligence owns TEXT -> legal analysis;
        # this is the seam between them, not a duplicate extraction path.
        source_document = await DocumentRepository(session, workspace_id).get(body.document_id)
        if source_document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
        if source_document.status != DocumentStatus.READY:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Document is not ready (status={source_document.status.value}) — "
                f"{source_document.processing_error or 'processing has not completed'}",
            )
        raw_text = source_document.extracted_text

    if not raw_text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Document has no extracted text to analyze")

    contract = Contract(
        workspace_id=workspace_id, title=body.title, contract_type=body.contract_type, document_id=body.document_id
    )
    contract = await ContractRepository(session, workspace_id).add(contract)
    await session.flush()

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    version = ContractVersion(
        workspace_id=workspace_id, contract_id=contract.id, version_number=1,
        content=raw_text, content_hash=content_hash, is_current=True,
    )
    session.add(version)
    await session.commit()
    return contract


@router.get("/contracts", response_model=list[ContractOut])
async def list_contracts(
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Contract]:
    return await ContractRepository(session, workspace_id).list()


@router.get("/contracts/{contract_id}", response_model=ContractOut)
async def get_contract(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Contract:
    return await _get_contract_or_404(session, workspace_id, contract_id)


@router.post(
    "/contracts/{contract_id}/analyze",
    dependencies=[Depends(rate_limit_by_workspace("contract_analyze", get_settings().rate_limit_llm_per_minute))],
)
async def analyze_contract(
    contract_id: uuid.UUID,
    body: AnalyzeRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    contract = await _get_contract_or_404(session, workspace_id, contract_id)
    version = await _get_current_version_or_404(session, contract.id)

    organization_id = await _resolve_organization_id(session, workspace_id)
    # AuditLog.user_id is a real FK to users.id; the dev-mode auth stub
    # (app/security/deps.py) fabricates an identity with no backing row, so
    # passing it through would violate the constraint — None is the honest
    # value until real JWT-backed users exist (LEGAL-ROADMAP.md).
    engine = ContractIntelligenceEngine(session, LLMGateway(), organization_id, workspace_id, user_id=None)
    try:
        review = await engine.analyze(
            contract, version, party_perspective=body.party_perspective, review_depth=body.review_depth,
            jurisdiction=body.jurisdiction, effective_at=body.effective_at, force=body.force,
        )
        await session.commit()
    except ContractAnalysisFailedError as exc:
        await session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Contract analysis failed: {exc}") from exc

    return {
        "review_id": str(review.id),
        "status": review.status.value,
        "overall_score": review.overall_score,
        "risk_summary": review.risk_summary,
        "executive_summary": review.executive_summary,
        "analysis_status": review.analysis_status.value,
    }


@router.post("/contracts/{contract_id}/review")
async def get_review(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    contract = await _get_contract_or_404(session, workspace_id, contract_id)
    version = await _get_current_version_or_404(session, contract.id)

    result = await session.execute(
        select(ContractReview).where(
            ContractReview.contract_id == contract.id, ContractReview.version_id == version.id,
            ContractReview.status == ContractReviewStatus.COMPLETED,
        ).order_by(ContractReview.created_at.desc())
    )
    review = result.scalars().first()
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No completed review for the current version — call /analyze first")

    return {
        "review_id": str(review.id),
        "status": review.status.value,
        "analysis_status": review.analysis_status.value,
        "overall_score": review.overall_score,
        "risk_summary": review.risk_summary,
        "executive_summary": review.executive_summary,
        "party_perspective": review.party_perspective.value,
        "review_depth": review.review_depth.value,
        "performance_ms": review.performance_ms,
    }


@router.post("/contracts/{contract_id}/redline")
async def get_redline(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    contract = await _get_contract_or_404(session, workspace_id, contract_id)
    result = await session.execute(select(RedlineChange).where(RedlineChange.contract_id == contract.id))
    changes = result.scalars().all()
    return [
        {
            "id": str(c.id), "clause_id": str(c.clause_id), "risk_id": str(c.risk_id) if c.risk_id else None,
            "research_id": c.research_id, "reason": c.reason, "diff_ops": c.diff_ops, "review_status": c.review_status.value,
        }
        for c in changes
    ]


class RedlineDecisionRequest(BaseModel):
    decision: RedlineReviewStatus  # "accepted" | "rejected" — never "proposed" (that's the initial state only)


@router.patch("/contracts/{contract_id}/redline/{change_id}")
async def decide_redline_change(
    contract_id: uuid.UUID,
    change_id: uuid.UUID,
    body: RedlineDecisionRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Explicit user-driven accept/reject of a proposed redline (brief §16) —
    the AI proposes diff_ops, it never applies them; only this endpoint,
    triggered by a human action, changes review_status.
    """
    if body.decision == RedlineReviewStatus.PROPOSED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "decision must be 'accepted' or 'rejected'")

    await _get_contract_or_404(session, workspace_id, contract_id)
    change = await session.get(RedlineChange, change_id)
    if change is None or change.contract_id != contract_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Redline change not found on this contract")

    change.review_status = body.decision
    await session.commit()

    logger.info(
        "redline_decision",
        workspace_id=str(workspace_id),
        user_id=str(user.user_id),
        contract_id=str(contract_id),
        change_id=str(change_id),
        decision=body.decision.value,
    )

    return {"id": str(change.id), "review_status": change.review_status.value}


@router.get("/contracts/{contract_id}/clauses")
async def list_clauses(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _get_contract_or_404(session, workspace_id, contract_id)
    result = await session.execute(select(ContractClause).where(ContractClause.contract_id == contract_id))
    clauses = result.scalars().all()
    return [
        {
            "id": str(c.id), "clause_number": c.clause_number, "clause_type": c.clause_type.value,
            "original_text": c.original_text, "position_start": c.position_start, "position_end": c.position_end,
            "confidence": c.confidence,
        }
        for c in clauses
    ]


@router.get("/contracts/{contract_id}/risks")
async def list_risks(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _get_contract_or_404(session, workspace_id, contract_id)
    result = await session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract_id))
    risks = result.scalars().all()
    return [
        {
            "id": str(r.id), "clause_id": str(r.clause_id) if r.clause_id else None, "risk_type": r.risk_type.value,
            "severity": r.severity.value, "category": r.category.value, "classification": r.classification.value,
            "title": r.title, "description": r.description, "why_it_matters": r.why_it_matters,
            "legal_basis": r.legal_basis, "confidence": r.confidence, "verification_status": r.verification_status.value,
            "citations": r.citations, "agreement_status": r.agreement_status.value,
        }
        for r in risks
    ]


@router.get("/contracts/{contract_id}/report")
async def get_report(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    contract = await _get_contract_or_404(session, workspace_id, contract_id)
    version = await _get_current_version_or_404(session, contract.id)

    review_result = await session.execute(
        select(ContractReview).where(
            ContractReview.contract_id == contract.id, ContractReview.version_id == version.id,
            ContractReview.status == ContractReviewStatus.COMPLETED,
        ).order_by(ContractReview.created_at.desc())
    )
    review = review_result.scalars().first()
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No completed review for the current version — call /analyze first")

    risks_result = await session.execute(select(ContractRisk).where(ContractRisk.contract_id == contract.id))
    risks = risks_result.scalars().all()

    recs_query = (
        select(ContractRecommendation).where(ContractRecommendation.risk_id.in_([r.id for r in risks]))
        if risks
        else select(ContractRecommendation).where(false())
    )
    recs_result = await session.execute(recs_query)
    recommendations = recs_result.scalars().all()
    recs_by_risk = {rec.risk_id: rec for rec in recommendations}

    alt_result = await session.execute(select(AlternativeClause))
    alternatives_by_clause = {a.original_clause_id: a for a in alt_result.scalars().all()}

    return {
        "contract_id": str(contract.id),
        "contract_type": contract.contract_type.value,
        "executive_summary": review.executive_summary,
        "overall_score": review.overall_score,
        "risk_summary": review.risk_summary,
        "risks": [
            {
                "id": str(r.id), "severity": r.severity.value, "category": r.category.value,
                "classification": r.classification.value, "title": r.title, "description": r.description,
                "why_it_matters": r.why_it_matters, "legal_basis": r.legal_basis,
                "verification_status": r.verification_status.value, "citations": r.citations,
                "clause_id": str(r.clause_id) if r.clause_id else None,
                "recommendation": (
                    {"action": recs_by_risk[r.id].action.value, "reason": recs_by_risk[r.id].reason}
                    if r.id in recs_by_risk else None
                ),
                "alternative_clause": (
                    {"proposed_text": alternatives_by_clause[r.clause_id].proposed_text,
                        "change_reason": alternatives_by_clause[r.clause_id].change_reason}
                    if r.clause_id and r.clause_id in alternatives_by_clause else None
                ),
            }
            for r in risks
        ],
        "performance_ms": review.performance_ms,
        "knowledge_snapshot": review.knowledge_snapshot,
        "analysis_status": review.analysis_status.value,
    }


class ContractSearchRequest(BaseModel):
    query: str


@router.post("/contracts/{contract_id}/search")
async def search_contract(
    contract_id: uuid.UUID,
    body: ContractSearchRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Real keyword search over already-extracted clauses (ILIKE) — not the
    hybrid Knowledge Base search (that's public legal sources, LEGAL-RAG.md);
    this searches the tenant's own contract text.
    """
    await _get_contract_or_404(session, workspace_id, contract_id)
    result = await session.execute(
        select(ContractClause).where(ContractClause.contract_id == contract_id, ContractClause.normalized_text.ilike(f"%{body.query}%"))
    )
    matches = result.scalars().all()
    return [
        {"clause_id": str(c.id), "clause_number": c.clause_number, "clause_type": c.clause_type.value, "excerpt": c.original_text[:300]}
        for c in matches
    ]


@router.get("/contracts/{contract_id}/versions")
async def list_versions(
    contract_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    await _get_contract_or_404(session, workspace_id, contract_id)
    result = await session.execute(
        select(ContractVersion).where(ContractVersion.contract_id == contract_id).order_by(ContractVersion.version_number)
    )
    return [
        {
            "id": str(v.id), "version_number": v.version_number, "is_current": v.is_current,
            "content_hash": v.content_hash, "created_at": v.created_at.isoformat(),
        }
        for v in result.scalars().all()
    ]


@router.get("/contracts/{contract_id}/diff")
async def diff_versions(
    contract_id: uuid.UUID,
    from_version_id: uuid.UUID,
    to_version_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _get_contract_or_404(session, workspace_id, contract_id)
    from_version = await session.get(ContractVersion, from_version_id)
    to_version = await session.get(ContractVersion, to_version_id)
    if from_version is None or to_version is None or from_version.contract_id != contract_id or to_version.contract_id != contract_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or both versions not found for this contract")

    extractor = ContractStructureExtractor()
    old_clauses = extractor.extract(from_version.content)
    new_clauses = extractor.extract(to_version.content)
    diff = diff_clauses(old_clauses, new_clauses)

    return {
        "added": [{"clause_number": c.clause_number, "text": c.original_text[:300]} for c in diff.added],
        "removed": [{"clause_number": c.clause_number, "text": c.original_text[:300]} for c in diff.removed],
        "changed": [
            {"clause_number": old.clause_number, "old_text": old.original_text[:300], "new_text": new.original_text[:300]}
            for old, new in diff.changed
        ],
        "unchanged_count": diff.unchanged_count,
    }


@router.get("/contracts/{contract_id}/export/{fmt}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def export_report(contract_id: uuid.UUID, fmt: str) -> None:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"Export to {fmt!r} is not implemented — see LEGAL-ROADMAP.md. Use GET /contracts/{{id}}/report for structured JSON.",
    )
