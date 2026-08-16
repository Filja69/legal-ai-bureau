"""GET /search/global — Phase 8 brief §12: tenant + public search, type-labeled."""
from __future__ import annotations

import pytest

from app.models.matters import Case
from tests.security.auth_factories import make_org_and_workspace


@pytest.mark.asyncio
async def test_global_search_finds_matching_case_and_labels_it(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    case = Case(workspace_id=workspace.id, title="Ivanov v. Petrov contract dispute")
    db_session.add(case)
    await db_session.commit()

    response = await client.get(
        "/api/v1/legal/search/global",
        params={"q": "Ivanov"},
        headers={"X-Workspace-Id": str(workspace.id)},
    )
    assert response.status_code == 200
    body = response.json()
    case_results = [r for r in body["results"] if r["type"] == "CASE"]
    assert any(r["id"] == str(case.id) for r in case_results)


@pytest.mark.asyncio
async def test_global_search_is_workspace_isolated(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Search Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Search Org B")
    case = Case(workspace_id=workspace_a.id, title="Confidential Matter Zephyr")
    db_session.add(case)
    await db_session.commit()

    response = await client.get(
        "/api/v1/legal/search/global",
        params={"q": "Zephyr"},
        headers={"X-Workspace-Id": str(workspace_b.id)},
    )
    assert response.status_code == 200
    case_results = [r for r in response.json()["results"] if r["type"] == "CASE"]
    assert case_results == []
