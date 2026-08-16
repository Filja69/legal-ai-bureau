"""Cases — LEGAL-API.md §Cases. The one resource implemented with real DB-backed
CRUD at scaffold stage (rather than 501) specifically to exercise and prove
out tenant isolation end-to-end (LEGAL-SECURITY.md §2) before Phase 2 builds
on top of it.

Phase 9.3 revision: real Litigation & Case Intelligence — parties, document
linking (reuses Phase 9.2 Document Intelligence, never duplicates uploaded
files), deterministic fact extraction with provenance, timeline, evidence
matrix, and contradiction detection. Explicitly NOT built this phase:
claims/defenses persistence, a persisted legal-issue tree, opponent
modeling, strategy generation, draft documents — `/strategy` and
`/deadlines` remain honest 501s. See docs/PHASE-9-3-LITIGATION-RESULT.md.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domains.litigation.pipeline import LitigationCaseEngine
from app.models.matters import (
    Case,
    CaseContradiction,
    CaseDocument,
    CaseEvent,
    CaseFact,
    CaseFactEvidence,
    CaseParty,
    Document,
)
from app.repositories.case_document_repository import CaseDocumentRepository
from app.repositories.case_party_repository import CasePartyRepository
from app.repositories.case_repository import CaseRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.case import CaseCreate, CaseOut
from app.schemas.litigation import (
    CaseContradictionOut,
    CaseDocumentAttach,
    CaseDocumentOut,
    CaseEventOut,
    CaseFactEvidenceOut,
    CaseFactOut,
    CasePartyCreate,
    CasePartyOut,
    EvidenceMatrixRowOut,
)
from app.security.deps import get_current_user, get_workspace_id

router = APIRouter(tags=["cases"])
logger = structlog.get_logger(__name__)


async def _get_case_or_404(session: AsyncSession, workspace_id: uuid.UUID, case_id: uuid.UUID) -> Case:
    case = await CaseRepository(session, workspace_id).get(case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found in this workspace")
    return case


@router.get("/cases", response_model=list[CaseOut])
async def list_cases(
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Case]:
    return await CaseRepository(session, workspace_id).list()


@router.post("/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Case:
    case = Case(workspace_id=workspace_id, **body.model_dump())
    case = await CaseRepository(session, workspace_id).add(case)
    await session.commit()
    return case


@router.get("/cases/{case_id}", response_model=CaseOut)
async def get_case(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Case:
    return await _get_case_or_404(session, workspace_id, case_id)


# --- Parties (brief §5) ---


@router.get("/cases/{case_id}/parties", response_model=list[CasePartyOut])
async def list_case_parties(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseParty]:
    await _get_case_or_404(session, workspace_id, case_id)
    result = await session.execute(select(CaseParty).where(CaseParty.case_id == case_id))
    return list(result.scalars().all())


@router.post("/cases/{case_id}/parties", response_model=CasePartyOut, status_code=status.HTTP_201_CREATED)
async def add_case_party(
    case_id: uuid.UUID,
    body: CasePartyCreate,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CaseParty:
    await _get_case_or_404(session, workspace_id, case_id)
    party = CaseParty(workspace_id=workspace_id, case_id=case_id, **body.model_dump())
    party = await CasePartyRepository(session, workspace_id).add(party)
    await session.commit()
    return party


# --- Documents (brief §6 — links, never duplicates, Phase 9.2 Documents) ---


@router.get("/cases/{case_id}/documents", response_model=list[CaseDocumentOut])
async def list_case_documents(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseDocumentOut]:
    await _get_case_or_404(session, workspace_id, case_id)
    result = await session.execute(select(CaseDocument).where(CaseDocument.case_id == case_id))
    case_documents = result.scalars().all()

    out: list[CaseDocumentOut] = []
    for cd in case_documents:
        document = await session.get(Document, cd.document_id)
        out.append(
            CaseDocumentOut(
                id=cd.id, case_id=cd.case_id, document_id=cd.document_id, role=cd.role,
                document_title=document.title if document else "(deleted)",
                document_status=document.status.value if document else "unknown",
            )
        )
    return out


@router.post("/cases/{case_id}/documents", response_model=CaseDocumentOut, status_code=status.HTTP_201_CREATED)
async def attach_case_document(
    case_id: uuid.UUID,
    body: CaseDocumentAttach,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CaseDocumentOut:
    await _get_case_or_404(session, workspace_id, case_id)
    document = await DocumentRepository(session, workspace_id).get(body.document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")

    existing = await session.execute(
        select(CaseDocument).where(CaseDocument.case_id == case_id, CaseDocument.document_id == body.document_id)
    )
    if existing.scalars().first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already attached to this case")

    case_document = CaseDocument(workspace_id=workspace_id, case_id=case_id, document_id=body.document_id, role=body.role)
    case_document = await CaseDocumentRepository(session, workspace_id).add(case_document)
    await session.commit()
    logger.info("case_document_attached", case_id=str(case_id), document_id=str(body.document_id), role=body.role.value)

    return CaseDocumentOut(
        id=case_document.id, case_id=case_id, document_id=body.document_id, role=body.role,
        document_title=document.title, document_status=document.status.value,
    )


# --- Facts (brief §7/§8) ---


def _fact_to_out(fact: CaseFact, evidence_rows: list[CaseFactEvidence], titles: dict[uuid.UUID, str]) -> CaseFactOut:
    return CaseFactOut(
        id=fact.id, case_id=fact.case_id, statement=fact.statement, fact_type=fact.fact_type,
        status=fact.status, normalized_value=fact.normalized_value, created_at=fact.created_at,
        evidence=[
            CaseFactEvidenceOut(
                document_id=e.document_id, document_title=titles.get(e.document_id, "(deleted)"),
                chunk_id=e.chunk_id, page_number=e.page_number, section_path=e.section_path, excerpt=e.excerpt,
            )
            for e in evidence_rows
            if e.case_fact_id == fact.id
        ],
    )


async def _load_facts_with_evidence(session: AsyncSession, case_id: uuid.UUID) -> list[CaseFactOut]:
    facts = (await session.execute(select(CaseFact).where(CaseFact.case_id == case_id))).scalars().all()
    if not facts:
        return []
    fact_ids = [f.id for f in facts]
    evidence_rows = (await session.execute(select(CaseFactEvidence).where(CaseFactEvidence.case_fact_id.in_(fact_ids)))).scalars().all()
    document_ids = {e.document_id for e in evidence_rows}
    titles: dict[uuid.UUID, str] = {}
    for document_id in document_ids:
        document = await session.get(Document, document_id)
        if document is not None:
            titles[document_id] = document.title
    return [_fact_to_out(f, list(evidence_rows), titles) for f in facts]


@router.get("/cases/{case_id}/facts", response_model=list[CaseFactOut])
async def list_case_facts(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseFactOut]:
    await _get_case_or_404(session, workspace_id, case_id)
    return await _load_facts_with_evidence(session, case_id)


@router.post("/cases/{case_id}/facts/extract", response_model=list[CaseFactOut])
async def extract_case_facts(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseFactOut]:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    await engine.extract_facts(case)
    await session.commit()
    return await _load_facts_with_evidence(session, case_id)


# --- Timeline (brief §10/§11) ---


@router.get("/cases/{case_id}/timeline", response_model=list[CaseEventOut])
async def get_case_timeline(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseEvent]:
    await _get_case_or_404(session, workspace_id, case_id)
    result = await session.execute(
        select(CaseEvent).where(CaseEvent.case_id == case_id).order_by(CaseEvent.event_date.is_(None), CaseEvent.event_date)
    )
    return list(result.scalars().all())


@router.post("/cases/{case_id}/timeline/build", response_model=list[CaseEventOut])
async def build_case_timeline(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseEvent]:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    events = await engine.build_timeline(case)
    await session.commit()
    return events


# --- Contradictions (brief §14) ---


@router.get("/cases/{case_id}/contradictions", response_model=list[CaseContradictionOut])
async def list_case_contradictions(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseContradictionOut]:
    await _get_case_or_404(session, workspace_id, case_id)
    rows = (await session.execute(select(CaseContradiction).where(CaseContradiction.case_id == case_id))).scalars().all()
    out: list[CaseContradictionOut] = []
    for row in rows:
        fact_a = await session.get(CaseFact, row.fact_a_id)
        fact_b = await session.get(CaseFact, row.fact_b_id)
        out.append(
            CaseContradictionOut(
                id=row.id, case_id=row.case_id, contradiction_type=row.contradiction_type, description=row.description,
                fact_a_id=row.fact_a_id, fact_a_statement=fact_a.statement if fact_a else "(deleted)",
                fact_b_id=row.fact_b_id, fact_b_statement=fact_b.statement if fact_b else "(deleted)",
            )
        )
    return out


# --- Evidence matrix (brief §12/§13) ---


@router.get("/cases/{case_id}/evidence-matrix", response_model=list[EvidenceMatrixRowOut])
async def get_evidence_matrix(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EvidenceMatrixRowOut]:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    rows = await engine.get_evidence_matrix(case)
    return [
        EvidenceMatrixRowOut(
            fact_statement=row.fact.statement, fact_type=row.fact.fact_type, normalized_value=row.fact.normalized_value,
            strength=row.strength.value, reasons=row.reasons, corroboration_count=row.fact.corroboration_count,
        )
        for row in rows
    ]


# --- One-shot analysis (brief §33's suggested POST /cases/{id}/analyze) ---


@router.post("/cases/{case_id}/analyze")
async def analyze_case(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Runs extract -> contradiction detection -> timeline build in one
    idempotent pass. Deliberately returns only counts, not the full payload
    — callers fetch /facts, /timeline, /contradictions, /evidence-matrix
    separately for the actual data, keeping this endpoint's response small
    and its purpose (a status/progress signal) clear.
    """
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    facts = await engine.extract_facts(case)
    contradictions = await engine.detect_and_persist_contradictions(case)
    events = await engine.build_timeline(case)
    await session.commit()

    logger.info(
        "case_analysis_completed", case_id=str(case_id), workspace_id=str(workspace_id),
        fact_count=len(facts), contradiction_count=len(contradictions), event_count=len(events),
    )
    return {
        "case_id": str(case_id),
        "fact_count": len(facts),
        "contradiction_count": len(contradictions),
        "event_count": len(events),
    }


@router.get("/cases/{case_id}/analysis")
async def get_case_analysis_summary(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """A computed summary, not a persisted row — there is no separate
    "case analysis" entity this phase (brief §48: avoid schema explosion).
    """
    await _get_case_or_404(session, workspace_id, case_id)
    fact_count = len((await session.execute(select(CaseFact).where(CaseFact.case_id == case_id))).scalars().all())
    contradiction_count = len(
        (await session.execute(select(CaseContradiction).where(CaseContradiction.case_id == case_id))).scalars().all()
    )
    event_count = len((await session.execute(select(CaseEvent).where(CaseEvent.case_id == case_id))).scalars().all())
    return {"case_id": str(case_id), "fact_count": fact_count, "contradiction_count": contradiction_count, "event_count": event_count}


# --- Explicitly out of scope this phase (brief §58's stop condition) ---


@router.post("/cases/{case_id}/strategy", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def litigation_strategy(case_id: uuid.UUID) -> None:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Strategy/opponent-model/counterargument generation is explicitly out of scope for Phase 9.3 — "
        "see docs/PHASE-9-3-LITIGATION-RESULT.md.",
    )


@router.get("/cases/{case_id}/deadlines", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def case_deadlines(case_id: uuid.UUID) -> None:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Procedural deadline/limitation-period analysis is explicitly out of scope for Phase 9.3 — "
        "never fabricated, not merely deferred.",
    )
