"""Pydantic request/response schemas for /contracts — mirrors LEGAL-API.md."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.contracts import ContractStatus, ContractType, PartyPerspective, ReviewDepth


class ContractCreate(BaseModel):
    title: str
    contract_type: ContractType = ContractType.UNKNOWN
    raw_text: str | None = None
    document_id: uuid.UUID | None = None


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    contract_type: ContractType
    status: ContractStatus
    is_mock: bool


class AnalyzeRequest(BaseModel):
    party_perspective: PartyPerspective = PartyPerspective.NEUTRAL
    review_depth: ReviewDepth = ReviewDepth.STANDARD
    jurisdiction: str = "RU"
    effective_at: date | None = None
    force: bool = False
