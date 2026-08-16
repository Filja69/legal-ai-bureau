"""API contract — LEGAL-API.md. Verifies routes exist with the right shape;
not-yet-implemented surfaces correctly report 501 rather than 404 (proves the
contract is real even before the business logic behind it is).
"""
from __future__ import annotations

import uuid

import pytest

from app.models.organization import Organization, Workspace


@pytest.mark.asyncio
async def test_cases_requires_workspace_header(client):
    response = await client.get("/api/v1/legal/cases")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_and_list_case_roundtrip(client, db_session):
    # cases.workspace_id is a real FK — the workspace must exist first.
    org = Organization(name="Test Org")
    db_session.add(org)
    await db_session.flush()
    workspace = Workspace(organization_id=org.id, name="Test Workspace")
    db_session.add(workspace)
    await db_session.commit()

    headers = {"X-Workspace-Id": str(workspace.id)}

    create_response = await client.post(
        "/api/v1/legal/cases", json={"title": "Взыскание задолженности"}, headers=headers
    )
    assert create_response.status_code == 201
    case_id = create_response.json()["id"]

    list_response = await client.get("/api/v1/legal/cases", headers=headers)
    assert list_response.status_code == 200
    assert any(c["id"] == case_id for c in list_response.json())


@pytest.mark.asyncio
async def test_create_contract_from_unknown_document_id_is_404(client, db_session):
    """Phase 4 revision: the flat `/analyze-contract` stub from Task #10 was
    replaced by the real nested `/contracts/{id}/analyze` pipeline
    (app/api/v1/contracts.py) — see LEGAL-API.md.

    Phase 9.2 revision: creating a contract from an uploaded document is now
    real (Document Intelligence -> Contract Intelligence integration) — a
    `document_id` that doesn't exist in the workspace is a 404, not the old
    unconditional 501. Needs `db_session` (not just `client`) now that this
    path actually queries the documents table, unlike the old unconditional-501
    branch it replaced.
    """
    headers = {"X-Workspace-Id": str(uuid.uuid4())}
    response = await client.post(
        "/api/v1/legal/contracts", json={"title": "t", "document_id": str(uuid.uuid4())}, headers=headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_and_ready_are_unauthenticated(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/ready")).status_code == 200
