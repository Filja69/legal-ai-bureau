from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.matters import CaseStatus


class CaseCreate(BaseModel):
    title: str
    client_name: str | None = None
    counterparty_name: str | None = None
    matter_type: str | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: CaseStatus
    client_name: str | None
    counterparty_name: str | None
    matter_type: str | None
