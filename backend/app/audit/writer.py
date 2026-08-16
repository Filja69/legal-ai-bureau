"""AuditLog writer — brief §60 (Phase 4 is the first phase to actually
persist audit events; Phase 1-3 only had the table). Every write goes
through this one function so coverage can't be forgotten per-caller
(LEGAL-DATABASE.md §6). Never pass contract/document full text — only
ids, counts, and short summaries (brief §60 "не логировать полный текст").
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def write_audit_event(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    ai_model_used: str | None = None,
    result_summary: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ai_model_used=ai_model_used,
        result_summary=result_summary,
    )
    session.add(entry)
    await session.flush()
    return entry


class ContractAuditActions:
    UPLOADED = "CONTRACT_UPLOADED"
    ANALYSIS_STARTED = "CONTRACT_ANALYSIS_STARTED"
    ANALYSIS_COMPLETED = "CONTRACT_ANALYSIS_COMPLETED"
    ANALYSIS_FAILED = "CONTRACT_ANALYSIS_FAILED"
    RISK_CREATED = "RISK_CREATED"
    RECOMMENDATION_CREATED = "RECOMMENDATION_CREATED"
    REDLINE_CREATED = "REDLINE_CREATED"
    REPORT_EXPORTED = "REPORT_EXPORTED"
