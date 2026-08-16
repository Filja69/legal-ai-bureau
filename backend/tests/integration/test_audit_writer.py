"""AuditLog writer — brief §60."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.audit.writer import ContractAuditActions, write_audit_event
from app.models.audit import AuditLog
from app.models.organization import Organization, Workspace


@pytest.mark.asyncio
async def test_write_audit_event_persists_row(db_session):
    org = Organization(name="Org")
    db_session.add(org)
    await db_session.flush()
    workspace = Workspace(organization_id=org.id, name="WS")
    db_session.add(workspace)
    await db_session.flush()

    entry = await write_audit_event(
        db_session, organization_id=org.id, workspace_id=workspace.id, user_id=None,
        action=ContractAuditActions.UPLOADED, target_type="contract", result_summary="uploaded 1 document",
    )
    await db_session.commit()

    result = await db_session.execute(select(AuditLog).where(AuditLog.id == entry.id))
    row = result.scalars().one()
    assert row.action == "CONTRACT_UPLOADED"
    assert row.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_write_audit_event_never_receives_full_document_text():
    """Structural guard: the writer's signature has no `content`/`text` field —
    a caller physically cannot pass full contract text through it.
    """
    import inspect

    from app.audit.writer import write_audit_event as fn

    params = set(inspect.signature(fn).parameters)
    assert not (params & {"content", "text", "document_text", "contract_text"})
