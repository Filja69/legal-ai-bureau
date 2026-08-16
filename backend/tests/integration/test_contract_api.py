"""Contract Intelligence API — LEGAL-API.md, Phase 4 brief §46."""
from __future__ import annotations

import uuid

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.legal_knowledge import LegalSource, SourceType
from app.models.organization import Organization, Workspace
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource

_CONTRACT_TEXT = """1. Предмет договора

1.1. Исполнитель обязуется оказать услуги, а Заказчик обязуется принять и оплатить услуги.

3. Ответственность сторон

3.1. Ответственность Исполнителя перед Заказчиком не ограничивается и наступает в полном объеме, включая косвенные убытки.

4. Расторжение

4.1. Заказчик вправе отказаться от исполнения договора в любое время без уведомления и без объяснения причин.
"""


async def _make_workspace(db_session) -> str:
    org = Organization(name="Org")
    db_session.add(org)
    await db_session.flush()
    ws = Workspace(organization_id=org.id, name="WS")
    db_session.add(ws)
    await db_session.commit()
    return str(ws.id)


@pytest.fixture
async def indexed_dataset(db_session):
    source = LegalSource(name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, is_mock=True)
    db_session.add(source)
    await db_session.flush()
    indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider())
    pipeline = IngestionPipeline(
        db_session, MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator(), indexer=indexer
    )
    await pipeline.ingest_source(source)
    await db_session.commit()
    return source


@pytest.mark.asyncio
async def test_create_contract_requires_text_or_document(client, db_session):
    workspace_id = await _make_workspace(db_session)
    response = await client.post("/api/v1/legal/contracts", json={"title": "t"}, headers={"X-Workspace-Id": workspace_id})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_contract_from_unknown_document_id_is_404(client, db_session):
    # Phase 9.2: Document -> Contract creation is real now; an unknown
    # document_id in this workspace is a 404, not the old unconditional 501.
    workspace_id = await _make_workspace(db_session)
    response = await client.post(
        "/api/v1/legal/contracts", json={"title": "t", "document_id": str(uuid.uuid4())}, headers={"X-Workspace-Id": workspace_id}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_and_get_contract(client, db_session):
    workspace_id = await _make_workspace(db_session)
    headers = {"X-Workspace-Id": workspace_id}

    create_response = await client.post(
        "/api/v1/legal/contracts", json={"title": "Test Contract", "contract_type": "service", "raw_text": _CONTRACT_TEXT}, headers=headers
    )
    assert create_response.status_code == 201
    contract_id = create_response.json()["id"]

    get_response = await client.get(f"/api/v1/legal/contracts/{contract_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "Test Contract"

    list_response = await client.get("/api/v1/legal/contracts", headers=headers)
    assert any(c["id"] == contract_id for c in list_response.json())


@pytest.mark.asyncio
async def test_full_contract_pipeline_via_api(client, db_session, indexed_dataset):
    workspace_id = await _make_workspace(db_session)
    headers = {"X-Workspace-Id": workspace_id}

    create_response = await client.post(
        "/api/v1/legal/contracts", json={"title": "Test Contract", "contract_type": "service", "raw_text": _CONTRACT_TEXT}, headers=headers
    )
    contract_id = create_response.json()["id"]

    analyze_response = await client.post(f"/api/v1/legal/contracts/{contract_id}/analyze", json={}, headers=headers)
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()
    assert analysis["status"] == "completed"
    assert analysis["overall_score"] < 100

    clauses_response = await client.get(f"/api/v1/legal/contracts/{contract_id}/clauses", headers=headers)
    assert clauses_response.status_code == 200
    assert len(clauses_response.json()) > 0

    risks_response = await client.get(f"/api/v1/legal/contracts/{contract_id}/risks", headers=headers)
    assert risks_response.status_code == 200
    assert len(risks_response.json()) > 0

    review_response = await client.post(f"/api/v1/legal/contracts/{contract_id}/review", headers=headers)
    assert review_response.status_code == 200

    report_response = await client.get(f"/api/v1/legal/contracts/{contract_id}/report", headers=headers)
    assert report_response.status_code == 200
    assert "risks" in report_response.json()

    versions_response = await client.get(f"/api/v1/legal/contracts/{contract_id}/versions", headers=headers)
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert len(versions) == 1
    assert versions[0]["is_current"] is True

    redline_response = await client.post(f"/api/v1/legal/contracts/{contract_id}/redline", headers=headers)
    assert redline_response.status_code == 200
    assert isinstance(redline_response.json(), list)
    changes = redline_response.json()

    if changes:
        change_id = changes[0]["id"]
        decision_response = await client.patch(
            f"/api/v1/legal/contracts/{contract_id}/redline/{change_id}",
            json={"decision": "accepted"},
            headers=headers,
        )
        assert decision_response.status_code == 200
        assert decision_response.json()["review_status"] == "accepted"

        reject_invalid = await client.patch(
            f"/api/v1/legal/contracts/{contract_id}/redline/{change_id}",
            json={"decision": "proposed"},
            headers=headers,
        )
        assert reject_invalid.status_code == 400


@pytest.mark.asyncio
async def test_review_before_analyze_is_404(client, db_session):
    workspace_id = await _make_workspace(db_session)
    headers = {"X-Workspace-Id": workspace_id}
    create_response = await client.post(
        "/api/v1/legal/contracts", json={"title": "t", "raw_text": _CONTRACT_TEXT}, headers=headers
    )
    contract_id = create_response.json()["id"]

    review_response = await client.post(f"/api/v1/legal/contracts/{contract_id}/review", headers=headers)
    assert review_response.status_code == 404


@pytest.mark.asyncio
async def test_search_contract_finds_matching_clause(client, db_session, indexed_dataset):
    workspace_id = await _make_workspace(db_session)
    headers = {"X-Workspace-Id": workspace_id}
    create_response = await client.post(
        "/api/v1/legal/contracts", json={"title": "t", "raw_text": _CONTRACT_TEXT}, headers=headers
    )
    contract_id = create_response.json()["id"]
    # Clauses only exist after analysis — structure extraction is part of
    # the analyze pipeline (app/domains/contracts/engine.py), not upload.
    await client.post(f"/api/v1/legal/contracts/{contract_id}/analyze", json={}, headers=headers)

    search_response = await client.post(
        f"/api/v1/legal/contracts/{contract_id}/search", json={"query": "ответственность"}, headers=headers
    )
    assert search_response.status_code == 200
    assert len(search_response.json()) >= 1


@pytest.mark.asyncio
async def test_export_report_is_501(client, db_session):
    workspace_id = await _make_workspace(db_session)
    response = await client.get(
        f"/api/v1/legal/contracts/{uuid.uuid4()}/export/pdf", headers={"X-Workspace-Id": workspace_id}
    )
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_contract_not_found_returns_404(client, db_session):
    workspace_id = await _make_workspace(db_session)
    response = await client.get(f"/api/v1/legal/contracts/{uuid.uuid4()}", headers={"X-Workspace-Id": workspace_id})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_contract_isolated_across_workspaces(client, db_session):
    workspace_a = await _make_workspace(db_session)
    workspace_b = await _make_workspace(db_session)

    create_response = await client.post(
        "/api/v1/legal/contracts", json={"title": "t", "raw_text": _CONTRACT_TEXT}, headers={"X-Workspace-Id": workspace_a}
    )
    contract_id = create_response.json()["id"]

    cross_response = await client.get(f"/api/v1/legal/contracts/{contract_id}", headers={"X-Workspace-Id": workspace_b})
    assert cross_response.status_code == 404
