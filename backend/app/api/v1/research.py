"""Legal Research — LEGAL-API.md §Legal Research.

Phase 3 revision: `/research` is the real Legal Research Engine endpoint
(app/domains/legal_research/engine.py) — question -> facts -> issues ->
research plan -> multi-stage retrieval -> evidence ranking -> IRAC reasoning
-> counterargument search -> conflict detection -> independent review ->
confidence, not a bare LLM call.

Phase 8 revision: results are now persisted to `legal_research_reports`
(the Research workspace needs a real "past research" list, not just a
single most-recent in-memory response — brief §5/§14) — `result`/`trace`
are the exact same serialized shapes as before, just also written to a row.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_session
from app.domains.legal_research.engine import LegalResearchEngine
from app.domains.legal_research.models import LegalResearchRequest as EngineRequest
from app.domains.legal_research.models import ResearchMode
from app.llm.prompt_safety import wrap_untrusted
from app.llm.routing.gateway import LLMGateway
from app.models.matters import DocumentStatus, LegalResearchReport, ResearchReportStatus
from app.rag.embeddings.base import get_embedding_provider
from app.rag.retrieval.tenant_document_retriever import TenantDocumentRetriever
from app.repositories.document_repository import DocumentRepository
from app.security.deps import CurrentUser, get_current_user, get_workspace_id
from app.security.rate_limit import rate_limit_by_workspace

router = APIRouter(tags=["research"])
logger = structlog.get_logger(__name__)

_IMPLEMENTED_MODES = {ResearchMode.QUICK_ANSWER, ResearchMode.LEGAL_RESEARCH, ResearchMode.LEGAL_OPINION}
_MAX_DOCUMENT_CHUNKS_PER_RESEARCH = 12


class ResearchRequest(BaseModel):
    question: str
    jurisdiction: str = "RU"
    effective_at: date | None = None
    case_context: str | None = None
    facts: list[str] = []
    case_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] = []
    requested_output: ResearchMode = ResearchMode.LEGAL_RESEARCH


async def _build_document_evidence_context(
    session: AsyncSession, workspace_id: uuid.UUID, document_ids: list[uuid.UUID], question: str
) -> str | None:
    """Phase 9.2 brief §22 — the Research Engine can use SPECIFIC, user-selected
    tenant documents as factual evidence, never the whole workspace by default
    (avoiding unnecessary sensitive-data exposure and irrelevant retrieval).
    The excerpt is clearly labeled DOCUMENT_EVIDENCE and delimited as
    untrusted content — a client's contract is evidence, never legal
    authority (brief §17), and its text is never trusted as instructions
    (brief §31, same `wrap_untrusted` mechanism as everywhere else).
    """
    if not document_ids:
        return None

    repo = DocumentRepository(session, workspace_id)
    documents = []
    for document_id in document_ids:
        document = await repo.get(document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Document {document_id} not found in this workspace")
        if document.status != DocumentStatus.READY:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Document {document_id} is not ready (status={document.status.value})",
            )
        documents.append(document)

    retriever = TenantDocumentRetriever(session, get_embedding_provider())
    chunks = await retriever.retrieve(
        workspace_id=workspace_id, query_text=question, document_ids=document_ids, top_k=_MAX_DOCUMENT_CHUNKS_PER_RESEARCH
    )
    if not chunks:
        return None

    titles = {d.id: d.title for d in documents}
    excerpt = "\n\n".join(
        f"[DOCUMENT_EVIDENCE — {titles.get(c.document_id, '?')}, "
        f"{'стр. ' + str(c.page_number) if c.page_number else c.section_path or 'без разметки'}]:\n{c.text}"
        for c in chunks
    )
    return wrap_untrusted(
        "user_provided_document_evidence",
        "The following excerpts are from the user's own uploaded documents — they are factual "
        "evidence about this specific matter, NOT legal authority (not a law, not a court decision). "
        "Never cite them as if they were a statute or case law.\n\n" + excerpt,
    )


@router.post(
    "/research",
    dependencies=[Depends(rate_limit_by_workspace("research", get_settings().rate_limit_llm_per_minute))],
)
async def research(
    body: ResearchRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.requested_output not in _IMPLEMENTED_MODES:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"research mode {body.requested_output.value!r} is an extension point (brief §39), not implemented in Phase 3. "
            f"Implemented modes: {sorted(m.value for m in _IMPLEMENTED_MODES)}",
        )

    document_context = await _build_document_evidence_context(session, workspace_id, body.document_ids, body.question)
    case_context = body.case_context
    if document_context:
        case_context = f"{case_context}\n\n{document_context}" if case_context else document_context

    engine_request = EngineRequest(
        question=body.question,
        jurisdiction=body.jurisdiction,
        effective_at=body.effective_at,
        case_context=case_context,
        facts=body.facts,
        requested_output=body.requested_output,
    )

    engine = LegalResearchEngine(session, LLMGateway())
    result, trace = await engine.run(engine_request)

    report = LegalResearchReport(
        workspace_id=workspace_id,
        user_id=None if user.is_dev_bypass else user.user_id,
        case_id=body.case_id,
        question=body.question,
        jurisdiction=body.jurisdiction,
        status=ResearchReportStatus(result.status),
        confidence=result.confidence.value,
        executive_conclusion=result.executive_conclusion,
        escalate_to_human=result.escalate_to_human,
        result_json=_serialize_result(result),
        trace_json=_serialize_trace(trace),
    )
    session.add(report)
    await session.commit()

    # Audit logging (brief §49) — workspace/user identity + which research ran,
    # without any document content. Full AuditLog table write is Phase 4
    # (app/models/audit.py exists but has no writer wired in yet); logged here
    # via structlog in the meantime so the event isn't silently dropped.
    logger.info(
        "research_completed",
        workspace_id=str(workspace_id),
        user_id=str(user.user_id),
        research_id=str(report.id),
        status=result.status,
        confidence=result.confidence.value,
        llm_calls=trace.llm_calls,
        total_ms=trace.performance_ms.get("total_ms"),
    )

    return {
        "research_id": str(report.id),
        "status": result.status,
        "result": report.result_json,
        "trace": report.trace_json,
    }


@router.get("/research")
async def list_research_reports(
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    case_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(LegalResearchReport).where(LegalResearchReport.workspace_id == workspace_id)
    count_stmt = select(func.count()).select_from(LegalResearchReport).where(LegalResearchReport.workspace_id == workspace_id)
    if case_id is not None:
        stmt = stmt.where(LegalResearchReport.case_id == case_id)
        count_stmt = count_stmt.where(LegalResearchReport.case_id == case_id)
    stmt = stmt.order_by(desc(LegalResearchReport.created_at)).limit(limit).offset(offset)

    reports = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()

    return {
        "total": total,
        "items": [
            {
                "id": str(r.id),
                "question": r.question,
                "jurisdiction": r.jurisdiction,
                "status": r.status.value,
                "confidence": r.confidence,
                "executive_conclusion": r.executive_conclusion,
                "escalate_to_human": r.escalate_to_human,
                "case_id": str(r.case_id) if r.case_id else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in reports
        ],
    }


@router.get("/research/{report_id}")
async def get_research_report(
    report_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    report = await session.get(LegalResearchReport, report_id)
    if report is None or report.workspace_id != workspace_id:
        # Same response for "doesn't exist" and "exists in another workspace"
        # — no cross-tenant existence signal (LEGAL-SECURITY.md §2).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research report not found")

    return {
        "research_id": str(report.id),
        "status": report.status.value,
        "result": report.result_json,
        "trace": report.trace_json,
        "created_at": report.created_at.isoformat(),
    }


def _serialize_result(result) -> dict:
    return {
        "executive_conclusion": result.executive_conclusion,
        "confidence": result.confidence.value,
        "issues": [
            {"id": i.id, "title": i.title, "description": i.description, "priority": i.priority, "issue_type": i.issue_type.value}
            for i in result.issues
        ],
        "facts": [
            {"subject": f.subject, "predicate": f.predicate, "object": f.object, "source": f.source.value, "confidence": f.confidence}
            for f in result.facts
        ],
        "claims": [
            {
                "claim": c.claim, "claim_type": c.claim_type, "importance": c.importance.value,
                "citations": c.citations, "verification_status": c.verification_status.value,
            }
            for c in result.claims
        ],
        "analysis": result.analysis,
        "counterarguments": result.counterarguments,
        "conflicts": [
            {
                "conflict_type": c.conflict_type.value, "description": c.description,
                "position_a": c.position_a, "position_b": c.position_b, "implication": c.implication,
            }
            for c in result.conflicts
        ],
        "risks": result.risks,
        "missing_facts": [{"question": m.question, "criticality": m.criticality.value, "reason": m.reason} for m in result.missing_facts],
        "recommended_actions": result.recommended_actions,
        "citations": result.citations,
        "citation_coverage": result.citation_coverage,
        "escalate_to_human": result.escalate_to_human,
        "escalation_reasons": result.escalation_reasons,
    }


def _serialize_trace(trace) -> dict:
    d = dataclasses.asdict(trace)
    d["created_at"] = trace.created_at.isoformat()
    if trace.knowledge_snapshot:
        d["knowledge_snapshot"]["captured_at"] = trace.knowledge_snapshot.captured_at.isoformat()
    return d
