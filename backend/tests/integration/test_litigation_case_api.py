"""Litigation & Case Intelligence API — Phase 9.3 brief §33/§34/§44/§54/§55.
Full pipeline against real Postgres: attach documents, extract facts,
build timeline, detect contradictions, evidence matrix, tenant isolation.
"""
from __future__ import annotations

import io

import pytest

from tests.security.auth_factories import make_org_and_workspace


async def _create_case(client, workspace_id, title="Test Dispute"):
    response = await client.post("/api/v1/legal/cases", json={"title": title}, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    return response.json()["id"]


async def _upload_ready_document(client, workspace_id, filename: str, text: str):
    files = {"file": (filename, io.BytesIO(text.encode("utf-8")), "text/plain")}
    response = await client.post("/api/v1/legal/documents", files=files, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    return body["id"]


@pytest.mark.asyncio
async def test_attach_document_to_case(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    document_id = await _upload_ready_document(client, workspace.id, "contract.txt", "1. Договор поставки.")

    attach = await client.post(
        f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id, "role": "contract"}, headers=headers
    )
    assert attach.status_code == 201
    assert attach.json()["role"] == "contract"

    list_response = await client.get(f"/api/v1/legal/cases/{case_id}/documents", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


@pytest.mark.asyncio
async def test_attach_same_document_twice_returns_409(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    document_id = await _upload_ready_document(client, workspace.id, "doc.txt", "1. Текст.")

    first = await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id}, headers=headers)
    assert first.status_code == 201
    second = await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id}, headers=headers)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_attach_nonexistent_document_returns_404(client, db_session):
    import uuid

    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}
    case_id = await _create_case(client, workspace.id)

    response = await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": str(uuid.uuid4())}, headers=headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_extract_facts_persists_with_provenance(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    document_id = await _upload_ready_document(
        client, workspace.id, "invoice.txt", "Сумма к оплате составляет 500 000 руб. Товар передан 10.03.2026."
    )
    await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id}, headers=headers)

    extract = await client.post(f"/api/v1/legal/cases/{case_id}/facts/extract", headers=headers)
    assert extract.status_code == 200
    facts = extract.json()
    assert len(facts) >= 2
    for fact in facts:
        assert fact["status"] == "supported"
        assert len(fact["evidence"]) >= 1
        assert fact["evidence"][0]["document_id"] == document_id


@pytest.mark.asyncio
async def test_extraction_is_idempotent(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    document_id = await _upload_ready_document(client, workspace.id, "doc.txt", "Оплата 01.01.2026 произведена.")
    await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id}, headers=headers)

    first = await client.post(f"/api/v1/legal/cases/{case_id}/facts/extract", headers=headers)
    second = await client.post(f"/api/v1/legal/cases/{case_id}/facts/extract", headers=headers)
    assert len(first.json()) == len(second.json())

    list_response = await client.get(f"/api/v1/legal/cases/{case_id}/facts", headers=headers)
    assert len(list_response.json()) == len(first.json())


@pytest.mark.asyncio
async def test_full_adversarial_pipeline_surfaces_contradictions(client, db_session):
    """The brief's own worked example (§55): invoice says 500,000 RUB,
    acceptance act says 450,000 RUB; email says delivery 10 March, act says
    delivery 12 March. The system must surface both as contradictions.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id, "Adversarial Dispute")

    invoice_id = await _upload_ready_document(
        client, workspace.id, "invoice.txt", "Сумма к оплате составляет 500 000 руб. Товар передан 10.03.2026."
    )
    act_id = await _upload_ready_document(
        client, workspace.id, "act.txt", "Согласно акту, стоимость составила 450 000 руб. Поставка произведена 12.03.2026."
    )
    email_id = await _upload_ready_document(client, workspace.id, "email.txt", "Уведомляем: доставка ожидается 10.03.2026.")

    for doc_id, role in [(invoice_id, "invoice"), (act_id, "act"), (email_id, "correspondence")]:
        resp = await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": doc_id, "role": role}, headers=headers)
        assert resp.status_code == 201

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200
    assert analyze.json()["contradiction_count"] == 2

    contradictions = await client.get(f"/api/v1/legal/cases/{case_id}/contradictions", headers=headers)
    types = {c["contradiction_type"] for c in contradictions.json()}
    assert types == {"date_mismatch", "amount_mismatch"}

    matrix = await client.get(f"/api/v1/legal/cases/{case_id}/evidence-matrix", headers=headers)
    assert any(row["strength"] == "conflicted" for row in matrix.json())

    timeline = await client.get(f"/api/v1/legal/cases/{case_id}/timeline", headers=headers)
    dates = [e["event_date"] for e in timeline.json()]
    assert dates == sorted(dates)


@pytest.mark.asyncio
async def test_missing_evidence_case_has_no_false_contradictions(client, db_session):
    """A case where documents simply don't overlap must not manufacture
    contradictions out of unrelated facts.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    document_id = await _upload_ready_document(client, workspace.id, "contract.txt", "Договор подписан 01.01.2026.")
    await client.post(f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id}, headers=headers)

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.json()["contradiction_count"] == 0


@pytest.mark.asyncio
async def test_add_and_list_case_party(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}
    case_id = await _create_case(client, workspace.id)

    create = await client.post(
        f"/api/v1/legal/cases/{case_id}/parties",
        json={"name": "ООО Ромашка", "party_type": "organization", "procedural_role": "plaintiff"},
        headers=headers,
    )
    assert create.status_code == 201
    assert create.json()["procedural_role"] == "plaintiff"

    list_response = await client.get(f"/api/v1/legal/cases/{case_id}/parties", headers=headers)
    assert len(list_response.json()) == 1


# --- Tenant isolation (brief §44) ---


@pytest.mark.asyncio
async def test_workspace_a_cannot_attach_document_to_workspace_b_case(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Litigation Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Litigation Org B")
    await db_session.commit()

    case_id = await _create_case(client, workspace_a.id)
    document_id = await _upload_ready_document(client, workspace_b.id, "b_doc.txt", "1. Текст.")

    response = await client.post(
        f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id}, headers={"X-Workspace-Id": str(workspace_b.id)}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workspace_a_cannot_extract_facts_for_workspace_b_case(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Litigation Org A2")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Litigation Org B2")
    await db_session.commit()

    case_id = await _create_case(client, workspace_a.id)
    response = await client.post(f"/api/v1/legal/cases/{case_id}/facts/extract", headers={"X-Workspace-Id": str(workspace_b.id)})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_workspace_a_cannot_read_workspace_b_facts_timeline_evidence_contradictions(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Litigation Org A3")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Litigation Org B3")
    await db_session.commit()
    headers_b = {"X-Workspace-Id": str(workspace_b.id)}

    case_id = await _create_case(client, workspace_a.id)

    assert (await client.get(f"/api/v1/legal/cases/{case_id}/facts", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/timeline", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/evidence-matrix", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/contradictions", headers=headers_b)).status_code == 404
    assert (await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/parties", headers=headers_b)).status_code == 404


@pytest.mark.asyncio
async def test_strategy_and_deadlines_remain_honest_501(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}
    case_id = await _create_case(client, workspace.id)

    strategy = await client.post(f"/api/v1/legal/cases/{case_id}/strategy", headers=headers)
    assert strategy.status_code == 501

    deadlines = await client.get(f"/api/v1/legal/cases/{case_id}/deadlines", headers=headers)
    assert deadlines.status_code == 501
