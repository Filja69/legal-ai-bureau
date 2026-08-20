from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.matters import (
    AllegationType,
    CaseDocumentRole,
    ContradictionType,
    DateType,
    FactStatus,
    FactType,
    PartyType,
    PaymentExecutionStatus,
    ProceduralRole,
)


class CasePartyCreate(BaseModel):
    name: str
    party_type: PartyType = PartyType.UNKNOWN
    procedural_role: ProceduralRole = ProceduralRole.UNKNOWN
    identifiers: dict = {}


class CasePartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    name: str
    party_type: PartyType
    procedural_role: ProceduralRole
    identifiers: dict


class CaseDocumentAttach(BaseModel):
    document_id: uuid.UUID
    role: CaseDocumentRole = CaseDocumentRole.OTHER


class CaseDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    role: CaseDocumentRole
    document_title: str
    document_status: str


class CaseFactEvidenceOut(BaseModel):
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID | None
    page_number: int | None
    section_path: str | None
    excerpt: str


class CaseFactOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    statement: str
    fact_type: FactType
    status: FactStatus
    normalized_value: str | None
    evidence: list[CaseFactEvidenceOut]
    created_at: datetime | None = None


class CaseEventOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    event_date: date | None
    date_type: DateType
    description: str
    event_type: str | None
    source_fact_id: uuid.UUID | None


class CaseContradictionOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    contradiction_type: ContradictionType
    description: str
    fact_a_id: uuid.UUID
    fact_a_statement: str
    fact_b_id: uuid.UUID
    fact_b_statement: str


class EvidenceMatrixRowOut(BaseModel):
    fact_statement: str
    fact_type: FactType
    normalized_value: str
    strength: str
    reasons: list[str]
    corroboration_count: int


# --- E1: case allegations ---


class CaseAllegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID | None
    page_number: int | None
    statement_text: str
    excerpt: str
    allegation_type: AllegationType
    created_at: datetime | None = None


# --- E3: structured payment orders ---


class CasePaymentOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    payment_date: date | None
    amount: str | None
    payer: str | None
    recipient: str | None
    payment_purpose: str | None
    referenced_contract_type: str | None
    referenced_contract_date: date | None
    referenced_contract_number: str | None
    execution_status: PaymentExecutionStatus
    excerpt: str


class MoneyFlowTransactionOut(BaseModel):
    payment_order_id: uuid.UUID
    document_id: uuid.UUID
    payment_date: date | None
    amount: str | None
    payer: str | None
    recipient: str | None
    referenced_contract_date: date | None


class MoneyFlowOut(BaseModel):
    transaction_count: int
    transactions: list[MoneyFlowTransactionOut]
    total_amount: str
    referenced_contract_dates: dict[str, int]
    referenced_contract_numbers: dict[str, int]


# --- E2: CLAIM_VS_EVIDENCE (computed, never persisted) ---


class ClaimEvidenceContradictionOut(BaseModel):
    contradiction_type: ContradictionType
    allegation_id: uuid.UUID
    allegation_document_id: uuid.UUID
    allegation_document_title: str
    allegation_page: int | None
    allegation_excerpt: str
    evidence_id: uuid.UUID
    evidence_document_id: uuid.UUID
    evidence_document_title: str
    evidence_page: int | None
    evidence_excerpt: str
    referenced_contract_date: date | None
    reason: str
    caveat: str
    confidence: str


# --- Case Result Summary (client-facing, template/deterministic synthesis) ---


class CaseSnapshotOut(BaseModel):
    party_names: list[str]
    document_count: int
    payment_count: int
    total_amount: str
    key_dates: list[tuple[date | None, str]]


class KeyFindingOut(BaseModel):
    severity: str
    statement: str
    source_document_id: uuid.UUID
    source_document_title: str
    page_number: int | None
    excerpt: str
    confidence: str
    caveat: str | None


class MissingEvidenceItemOut(BaseModel):
    priority: str
    description: str
    why_it_matters: str


class NextBestActionOut(BaseModel):
    priority: int
    action: str
    why: str


class CaseResultSummaryOut(BaseModel):
    case_snapshot: CaseSnapshotOut
    key_findings: list[KeyFindingOut]
    money_flow: MoneyFlowOut
    what_this_may_mean: list[str]
    missing_critical_evidence: list[MissingEvidenceItemOut]
    next_best_actions: list[NextBestActionOut]
    legal_kb_warning: str | None
