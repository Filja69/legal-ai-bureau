"""Chat — secondary entry point (LEGAL-API.md, LEGAL-PRD.md §5). Routes into the
product surfaces below via the Orchestrator. Scaffold stage: contract is real,
routing logic is not — returns 501 until the Orchestrator is wired to real agents.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.security.deps import get_current_user, get_workspace_id

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    case_id: uuid.UUID | None = None
    attachments: list[uuid.UUID] = []


class ConclusionRef(BaseModel):
    type: str
    id: uuid.UUID


class ChatResponse(BaseModel):
    reply: str
    conclusion_ref: ConclusionRef | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
) -> ChatResponse:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Chat routing to specialist agents is Phase 2 work.")
