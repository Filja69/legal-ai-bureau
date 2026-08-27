from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from app.models.matters import CaseStatus


class CaseCreate(BaseModel):
    title: str
    client_name: str | None = None
    counterparty_name: str | None = None
    matter_type: str | None = None


class CaseUpdate(BaseModel):
    """Partial update — every field optional, only fields the caller sets
    are changed. Exists so case-setup mistakes (e.g. `client_name` pointing
    at the wrong party) can be corrected without deleting and re-creating
    the case and re-attaching every document.
    """

    title: str | None = None
    client_name: str | None = None
    counterparty_name: str | None = None
    matter_type: str | None = None
    status: CaseStatus | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: CaseStatus
    client_name: str | None
    counterparty_name: str | None
    matter_type: str | None
