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
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.research import ResearchRequest, research
from app.db.session import get_session
from app.domains.legal_research.models import ResearchMode
from app.domains.litigation.pipeline import LitigationCaseEngine
from app.models.matters import (
    Case,
    CaseAllegation,
    CaseContradiction,
    CaseDocument,
    CaseEvent,
    CaseFact,
    CaseFactEvidence,
    CaseParty,
    CasePaymentOrder,
    Document,
)
from app.repositories.case_document_repository import CaseDocumentRepository
from app.repositories.case_party_repository import CasePartyRepository
from app.repositories.case_repository import CaseRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.case import CaseCreate, CaseOut
from app.schemas.litigation import (
    CaseAllegationOut,
    CaseContradictionOut,
    CaseDocumentAttach,
    CaseDocumentOut,
    CaseEventOut,
    CaseFactEvidenceOut,
    CaseFactOut,
    CasePartyCreate,
    CasePartyOut,
    CasePaymentOrderOut,
    CaseResultSummaryOut,
    CaseSnapshotOut,
    ClaimEvidenceContradictionOut,
    EvidenceMatrixRowOut,
    KeyFindingOut,
    MissingEvidenceItemOut,
    MoneyFlowOut,
    MoneyFlowTransactionOut,
    NextBestActionOut,
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


# --- Allegations (E1 — claims found in a party's own pleading text) ---


async def _document_titles(session: AsyncSession, document_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    titles: dict[uuid.UUID, str] = {}
    for document_id in document_ids:
        document = await session.get(Document, document_id)
        if document is not None:
            titles[document_id] = document.title
    return titles


async def _load_allegations(session: AsyncSession, case_id: uuid.UUID) -> list[CaseAllegationOut]:
    allegations = (await session.execute(select(CaseAllegation).where(CaseAllegation.case_id == case_id))).scalars().all()
    titles = await _document_titles(session, {a.document_id for a in allegations})
    return [
        CaseAllegationOut(
            id=a.id, case_id=a.case_id, document_id=a.document_id, document_title=titles.get(a.document_id, "(deleted)"),
            chunk_id=a.chunk_id, page_number=a.page_number, statement_text=a.statement_text, excerpt=a.excerpt,
            allegation_type=a.allegation_type, created_at=a.created_at,
        )
        for a in allegations
    ]


@router.get("/cases/{case_id}/allegations", response_model=list[CaseAllegationOut])
async def list_case_allegations(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseAllegationOut]:
    await _get_case_or_404(session, workspace_id, case_id)
    return await _load_allegations(session, case_id)


@router.post("/cases/{case_id}/allegations/extract", response_model=list[CaseAllegationOut])
async def extract_case_allegations(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CaseAllegationOut]:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    await engine.extract_allegations(case)
    await session.commit()
    return await _load_allegations(session, case_id)


# --- Payment orders (E3 — structured extraction) + Money Flow ---


@router.get("/cases/{case_id}/payment-orders", response_model=list[CasePaymentOrderOut])
async def list_case_payment_orders(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CasePaymentOrderOut]:
    await _get_case_or_404(session, workspace_id, case_id)
    orders = (await session.execute(select(CasePaymentOrder).where(CasePaymentOrder.case_id == case_id))).scalars().all()
    titles = await _document_titles(session, {o.document_id for o in orders})
    return [
        CasePaymentOrderOut(
            id=o.id, case_id=o.case_id, document_id=o.document_id, document_title=titles.get(o.document_id, "(deleted)"),
            page_number=o.page_number, payment_date=o.payment_date, amount=o.amount, payer=o.payer, recipient=o.recipient,
            payment_purpose=o.payment_purpose, referenced_contract_type=o.referenced_contract_type,
            referenced_contract_date=o.referenced_contract_date, referenced_contract_number=o.referenced_contract_number,
            execution_status=o.execution_status, excerpt=o.excerpt,
        )
        for o in orders
    ]


@router.post("/cases/{case_id}/payment-orders/extract", response_model=list[CasePaymentOrderOut])
async def extract_case_payment_orders(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[CasePaymentOrderOut]:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    await engine.extract_payment_orders(case)
    await session.commit()
    return await list_case_payment_orders(case_id, workspace_id, user, session)


@router.get("/cases/{case_id}/money-flow", response_model=MoneyFlowOut)
async def get_case_money_flow(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MoneyFlowOut:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    summary = await engine.get_money_flow(case)
    return MoneyFlowOut(
        transaction_count=summary.transaction_count,
        transactions=[
            MoneyFlowTransactionOut(
                payment_order_id=t.payment_order_id, document_id=t.document_id, payment_date=t.payment_date,
                amount=t.amount, payer=t.payer, recipient=t.recipient, referenced_contract_date=t.referenced_contract_date,
            )
            for t in summary.transactions
        ],
        total_amount=summary.total_amount,
        referenced_contract_dates=summary.referenced_contract_dates,
        referenced_contract_numbers=summary.referenced_contract_numbers,
    )


# --- Claim vs. Evidence (E2 — computed, never persisted) ---


@router.get("/cases/{case_id}/claim-evidence-contradictions", response_model=list[ClaimEvidenceContradictionOut])
async def get_claim_evidence_contradictions(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ClaimEvidenceContradictionOut]:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    contradictions = await engine.get_claim_evidence_contradictions(case)
    document_ids = {c.allegation_document_id for c in contradictions} | {c.evidence_document_id for c in contradictions}
    titles = await _document_titles(session, document_ids)
    return [
        ClaimEvidenceContradictionOut(
            contradiction_type=c.contradiction_type,
            allegation_id=c.allegation_id, allegation_document_id=c.allegation_document_id,
            allegation_document_title=titles.get(c.allegation_document_id, "(deleted)"),
            allegation_page=c.allegation_page, allegation_excerpt=c.allegation_excerpt,
            evidence_id=c.evidence_id, evidence_document_id=c.evidence_document_id,
            evidence_document_title=titles.get(c.evidence_document_id, "(deleted)"),
            evidence_page=c.evidence_page, evidence_excerpt=c.evidence_excerpt,
            referenced_contract_date=c.referenced_contract_date, reason=c.reason, caveat=c.caveat, confidence=c.confidence,
        )
        for c in contradictions
    ]


# --- Case -> Legal Research (E4) ---


class CaseResearchRequest(BaseModel):
    question: str
    jurisdiction: str = "RU"
    effective_at: date | None = None


@router.post("/cases/{case_id}/research")
async def research_case(
    case_id: uuid.UUID,
    body: CaseResearchRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Thin wrapper, not a parallel Research Engine: resolves this case's
    attached document_ids (tenant-scoped, same 404 as every other case
    endpoint) and forwards straight into the existing POST /research
    handler — identical retrieval/CitationValidator/fail-closed behavior,
    identical LOW-confidence/no-verified-rules honesty when the Knowledge
    Base doesn't have what's needed.
    """
    await _get_case_or_404(session, workspace_id, case_id)
    case_documents = (await session.execute(select(CaseDocument).where(CaseDocument.case_id == case_id))).scalars().all()
    document_ids = [cd.document_id for cd in case_documents]

    research_request = ResearchRequest(
        question=body.question,
        jurisdiction=body.jurisdiction,
        effective_at=body.effective_at,
        case_id=case_id,
        document_ids=document_ids,
        requested_output=ResearchMode.LEGAL_RESEARCH,
    )
    return await research(research_request, workspace_id=workspace_id, user=user, session=session)


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
    allegations = await engine.extract_allegations(case)
    payment_orders = await engine.extract_payment_orders(case)
    await session.commit()
    claim_evidence_contradictions = await engine.get_claim_evidence_contradictions(case)

    logger.info(
        "case_analysis_completed", case_id=str(case_id), workspace_id=str(workspace_id),
        fact_count=len(facts), contradiction_count=len(contradictions), event_count=len(events),
        allegation_count=len(allegations), payment_order_count=len(payment_orders),
        claim_evidence_contradiction_count=len(claim_evidence_contradictions),
    )
    return {
        "case_id": str(case_id),
        "fact_count": len(facts),
        "contradiction_count": len(contradictions),
        "event_count": len(events),
        "allegation_count": len(allegations),
        "payment_order_count": len(payment_orders),
        "claim_evidence_contradiction_count": len(claim_evidence_contradictions),
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
    case = await _get_case_or_404(session, workspace_id, case_id)
    fact_count = len((await session.execute(select(CaseFact).where(CaseFact.case_id == case_id))).scalars().all())
    contradiction_count = len(
        (await session.execute(select(CaseContradiction).where(CaseContradiction.case_id == case_id))).scalars().all()
    )
    event_count = len((await session.execute(select(CaseEvent).where(CaseEvent.case_id == case_id))).scalars().all())
    allegation_count = len((await session.execute(select(CaseAllegation).where(CaseAllegation.case_id == case_id))).scalars().all())
    payment_order_count = len(
        (await session.execute(select(CasePaymentOrder).where(CasePaymentOrder.case_id == case_id))).scalars().all()
    )
    claim_evidence_contradiction_count = len(await LitigationCaseEngine(session).get_claim_evidence_contradictions(case))
    return {
        "case_id": str(case_id),
        "fact_count": fact_count,
        "contradiction_count": contradiction_count,
        "event_count": event_count,
        "allegation_count": allegation_count,
        "payment_order_count": payment_order_count,
        "claim_evidence_contradiction_count": claim_evidence_contradiction_count,
    }


# --- Case Result Summary (client-facing, template/deterministic synthesis
# over already-persisted E1-E4 data — run POST /analyze first). ---


@router.get("/cases/{case_id}/result-summary", response_model=CaseResultSummaryOut)
async def get_case_result_summary(
    case_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CaseResultSummaryOut:
    case = await _get_case_or_404(session, workspace_id, case_id)
    engine = LitigationCaseEngine(session)
    summary = await engine.get_result_summary(case)
    return CaseResultSummaryOut(
        case_snapshot=CaseSnapshotOut(
            party_names=summary.case_snapshot.party_names,
            document_count=summary.case_snapshot.document_count,
            payment_count=summary.case_snapshot.payment_count,
            total_amount=summary.case_snapshot.total_amount,
            key_dates=summary.case_snapshot.key_dates,
        ),
        key_findings=[
            KeyFindingOut(
                severity=f.severity, statement=f.statement, source_document_id=f.source_document_id,
                source_document_title=f.source_document_title, page_number=f.page_number, excerpt=f.excerpt,
                confidence=f.confidence, caveat=f.caveat,
            )
            for f in summary.key_findings
        ],
        money_flow=MoneyFlowOut(
            transaction_count=summary.money_flow.transaction_count,
            transactions=[
                MoneyFlowTransactionOut(
                    payment_order_id=t.payment_order_id, document_id=t.document_id, payment_date=t.payment_date,
                    amount=t.amount, payer=t.payer, recipient=t.recipient, referenced_contract_date=t.referenced_contract_date,
                )
                for t in summary.money_flow.transactions
            ],
            total_amount=summary.money_flow.total_amount,
            referenced_contract_dates=summary.money_flow.referenced_contract_dates,
            referenced_contract_numbers=summary.money_flow.referenced_contract_numbers,
        ),
        what_this_may_mean=summary.what_this_may_mean,
        missing_critical_evidence=[
            MissingEvidenceItemOut(priority=i.priority, description=i.description, why_it_matters=i.why_it_matters)
            for i in summary.missing_critical_evidence
        ],
        next_best_actions=[
            NextBestActionOut(priority=a.priority, action=a.action, why=a.why) for a in summary.next_best_actions
        ],
        legal_kb_warning=summary.legal_kb_warning,
    )


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
