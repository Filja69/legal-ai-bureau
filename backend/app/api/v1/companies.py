"""Companies (Corporate + Due Diligence) — LEGAL-API.md §Companies."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.security.deps import get_current_user, get_workspace_id

router = APIRouter(tags=["companies"])


class CompanyCreate(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    name: str | None = None


class DueDiligenceRequest(BaseModel):
    inn: str | None = None
    ogrn: str | None = None
    name: str | None = None


@router.get("/companies", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_companies(workspace_id: uuid.UUID = Depends(get_workspace_id), user=Depends(get_current_user)) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "CompanyProfile module is Phase 5 work.")


@router.post("/companies", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_company(
    body: CompanyCreate, workspace_id: uuid.UUID = Depends(get_workspace_id), user=Depends(get_current_user)
) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "CompanyProfile module is Phase 5 work.")


@router.get("/companies/{company_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_company(
    company_id: uuid.UUID, workspace_id: uuid.UUID = Depends(get_workspace_id), user=Depends(get_current_user)
) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "CompanyProfile + timeline is Phase 5 work.")


@router.post("/due-diligence", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def due_diligence(
    body: DueDiligenceRequest, workspace_id: uuid.UUID = Depends(get_workspace_id), user=Depends(get_current_user)
) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Due Diligence Agent report generation is Phase 5 work.")


@router.get("/due-diligence/{report_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_due_diligence_report(
    report_id: uuid.UUID, workspace_id: uuid.UUID = Depends(get_workspace_id), user=Depends(get_current_user)
) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Due Diligence report persistence is Phase 5 work.")
