from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.matters import CaseDocumentRole, ContradictionType, DateType, FactStatus, FactType, PartyType, ProceduralRole


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
