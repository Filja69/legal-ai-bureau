"""Documents — LEGAL-API.md §Documents. Phase 8 added GET /documents (list);
Phase 9.2 added real upload validation + synchronous processing (upload now
returns the document already processed, not merely "uploaded" — see
tests/integration/test_document_pipeline.py for the full pipeline suite).
"""
from __future__ import annotations

import io

import pytest

from tests.security.auth_factories import make_org_and_workspace


@pytest.mark.asyncio
async def test_list_documents_empty_for_new_workspace(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    response = await client.get("/api/v1/legal/documents", headers={"X-Workspace-Id": str(workspace.id)})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_upload_then_list_shows_the_document(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    files = {"file": ("contract.txt", io.BytesIO(b"hello world"), "text/plain")}
    upload_response = await client.post("/api/v1/legal/documents", files=files, headers=headers)
    assert upload_response.status_code == 201
    uploaded = upload_response.json()
    assert uploaded["status"] == "ready"  # Phase 9.2 — upload now synchronously processes to completion
    assert uploaded["title"] == "contract.txt"

    list_response = await client.get("/api/v1/legal/documents", headers=headers)
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 1
    assert items[0]["id"] == uploaded["id"]


@pytest.mark.asyncio
async def test_list_documents_is_workspace_isolated(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Docs Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Docs Org B")
    await db_session.commit()

    files = {"file": ("secret.txt", io.BytesIO(b"secret"), "text/plain")}
    await client.post("/api/v1/legal/documents", files=files, headers={"X-Workspace-Id": str(workspace_a.id)})

    other_workspace_list = await client.get("/api/v1/legal/documents", headers={"X-Workspace-Id": str(workspace_b.id)})
    assert other_workspace_list.json() == []
