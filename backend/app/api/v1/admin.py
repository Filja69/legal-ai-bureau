"""Legal Knowledge Admin Panel API — LEGAL-API.md §Admin, requires Admin/Owner role.

`/admin/sources` and `/admin/index-status` were superseded by the real
`/knowledge/sources` and `/knowledge/index-status` endpoints (app/api/v1/
knowledge.py) in Phase 2 — see LEGAL-API.md's revision note. Only the
genuinely not-yet-built admin surfaces remain here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.organization import RoleName
from app.security.deps import require_role

router = APIRouter(tags=["admin"])


@router.get("/admin/errors", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def admin_errors(user=Depends(require_role(RoleName.ADMIN))) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Error/observability dashboard is Phase 3 work.")


@router.get("/admin/audit-log", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def admin_audit_log(user=Depends(require_role(RoleName.ADMIN))) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Audit log query API is Phase 3 work — AuditLog model already exists.")
