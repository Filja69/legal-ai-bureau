"""Persisted LegalResearchReport — Phase 8 (brief §5/§14: the Research
workspace needs a real "past research" list, not just the single most
recent in-memory response).
"""
from __future__ import annotations

import uuid

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.legal_knowledge import LegalSource, SourceType
from app.models.matters import Case
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource
from tests.security.auth_factories import make_org_and_workspace


async def _ingest_mock_dataset(db_session) -> LegalSource:
    source = LegalSource(name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, provider="mock", is_mock=True)
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
async def test_research_persists_and_is_retrievable_by_id(client, db_session):
    await _ingest_mock_dataset(db_session)
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    post_response = await client.post(
        "/api/v1/legal/research", json={"question": "надлежащим образом исполнение обязательства"}, headers=headers
    )
    assert post_response.status_code == 200
    research_id = post_response.json()["research_id"]

    get_response = await client.get(f"/api/v1/legal/research/{research_id}", headers=headers)
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["research_id"] == research_id
    assert body["result"] == post_response.json()["result"]


@pytest.mark.asyncio
async def test_research_list_returns_past_reports_newest_first(client, db_session):
    await _ingest_mock_dataset(db_session)
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    await client.post("/api/v1/legal/research", json={"question": "первый вопрос"}, headers=headers)
    await client.post("/api/v1/legal/research", json={"question": "второй вопрос"}, headers=headers)

    list_response = await client.get("/api/v1/legal/research", headers=headers)
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 2
    assert [item["question"] for item in body["items"]] == ["второй вопрос", "первый вопрос"]


@pytest.mark.asyncio
async def test_research_report_not_visible_from_another_workspace(client, db_session):
    await _ingest_mock_dataset(db_session)
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Research Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Research Org B")
    await db_session.commit()

    post_response = await client.post(
        "/api/v1/legal/research", json={"question": "test"}, headers={"X-Workspace-Id": str(workspace_a.id)}
    )
    research_id = post_response.json()["research_id"]

    cross_tenant_response = await client.get(
        f"/api/v1/legal/research/{research_id}", headers={"X-Workspace-Id": str(workspace_b.id)}
    )
    assert cross_tenant_response.status_code == 404


@pytest.mark.asyncio
async def test_research_get_unknown_id_is_404(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    response = await client.get(
        f"/api/v1/legal/research/{uuid.uuid4()}", headers={"X-Workspace-Id": str(workspace.id)}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_research_list_filters_by_case_id(client, db_session):
    await _ingest_mock_dataset(db_session)
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case = Case(workspace_id=workspace.id, title="Test Case")
    db_session.add(case)
    await db_session.commit()
    case_id = str(case.id)

    await client.post("/api/v1/legal/research", json={"question": "case-linked", "case_id": case_id}, headers=headers)
    await client.post("/api/v1/legal/research", json={"question": "unrelated"}, headers=headers)

    filtered = await client.get("/api/v1/legal/research", params={"case_id": case_id}, headers=headers)
    body = filtered.json()
    assert body["total"] == 1
    assert body["items"][0]["question"] == "case-linked"
