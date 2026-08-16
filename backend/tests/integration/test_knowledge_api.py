"""Real /search, /research, /knowledge/* API — LEGAL-API.md, Phase 2 brief §33-36."""
from __future__ import annotations

import uuid

import pytest

from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.legal_knowledge import LegalSource, SourceType
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.sources.mock.mock_source import MockLegalDataSource
from tests.security.auth_factories import make_org_and_workspace


async def _ingest_mock_dataset(db_session) -> LegalSource:
    source = LegalSource(
        name="Mock Legal Dataset", type=SourceType.USER_UPLOAD, provider="mock", is_mock=True, is_official=False
    )
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
async def test_search_endpoint_returns_real_results(client, db_session):
    await _ingest_mock_dataset(db_session)

    response = await client.get(
        "/api/v1/legal/search",
        params={"q": "надлежащим образом", "mode": "hybrid"},
        headers={"X-Workspace-Id": str(uuid.uuid4())},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["retrieval"]["keyword"] is True
    assert body["retrieval"]["vector"] is True


@pytest.mark.asyncio
async def test_search_endpoint_rejects_invalid_mode(client, db_session):
    response = await client.get("/api/v1/legal/search", params={"q": "x", "mode": "bogus"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_research_endpoint_returns_structured_research_result(client, db_session):
    """Phase 3 revision: /research is now the real Research Engine endpoint
    (see app/domains/legal_research/engine.py), not the Phase 2 evidence-only
    stub — response shape is {research_id, status, result, trace}.
    """
    await _ingest_mock_dataset(db_session)
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    response = await client.post(
        "/api/v1/legal/research", json={"question": "надлежащим образом исполнение обязательства"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["research_id"]
    assert body["status"] in ("completed", "blocked_unverified_claim", "research_failed")
    assert len(body["result"]["claims"]) >= 1
    assert body["result"]["citation_coverage"] >= 0
    assert body["trace"]["knowledge_snapshot"]["total_chunks"] > 0


@pytest.mark.asyncio
async def test_research_endpoint_low_confidence_for_irrelevant_question(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}
    response = await client.post(
        "/api/v1/legal/research", json={"question": "совершенно нерелевантный запрос ничего не найдет xyz123"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["confidence"] != "high"


@pytest.mark.asyncio
async def test_research_endpoint_rejects_unimplemented_mode(client, db_session):
    headers = {"X-Workspace-Id": str(uuid.uuid4())}
    response = await client.post(
        "/api/v1/legal/research",
        json={"question": "q", "requested_output": "case_analysis"},
        headers=headers,
    )
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_knowledge_sources_list(client, db_session):
    await _ingest_mock_dataset(db_session)
    response = await client.get("/api/v1/legal/knowledge/sources")
    assert response.status_code == 200
    sources = response.json()
    assert any(s["is_mock"] for s in sources)


@pytest.mark.asyncio
async def test_knowledge_source_sync_ingests_dataset(client, db_session):
    source = LegalSource(name="Mock", type=SourceType.USER_UPLOAD, provider="mock", is_mock=True)
    db_session.add(source)
    await db_session.commit()

    response = await client.post(f"/api/v1/legal/knowledge/sources/{source.id}/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["ingested"] > 0


@pytest.mark.asyncio
async def test_knowledge_source_sync_unknown_provider_returns_501(client, db_session):
    source = LegalSource(name="Unimplemented", type=SourceType.OFFICIAL_GOV, provider="pravo_gov_ru")
    db_session.add(source)
    await db_session.commit()

    response = await client.post(f"/api/v1/legal/knowledge/sources/{source.id}/sync")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_knowledge_documents_and_index_status(client, db_session):
    await _ingest_mock_dataset(db_session)

    documents = await client.get("/api/v1/legal/knowledge/documents")
    assert documents.status_code == 200
    assert len(documents.json()) > 0

    status_response = await client.get("/api/v1/legal/knowledge/index-status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["total_chunks"] > 0
    assert body["mock_chunks"] == body["total_chunks"]


@pytest.mark.asyncio
async def test_knowledge_document_reindex(client, db_session):
    await _ingest_mock_dataset(db_session)
    documents = (await client.get("/api/v1/legal/knowledge/documents")).json()
    chunk_id = documents[0]["chunk_id"]

    response = await client.post(f"/api/v1/legal/knowledge/documents/{chunk_id}/reindex")
    assert response.status_code == 200
    assert response.json()["reindexed"] is True


@pytest.mark.asyncio
async def test_index_status_reports_active_embedding_and_namespaces(client, db_session):
    await _ingest_mock_dataset(db_session)

    response = await client.get("/api/v1/legal/knowledge/index-status")
    assert response.status_code == 200
    body = response.json()
    assert body["active_embedding"]["provider"] == "mock"
    assert body["active_embedding"]["namespace"] in body["by_namespace"]
    assert body["active_embedding"]["chunks_in_active_namespace"] == body["total_chunks"]
    assert body["pending_embeddings"] == 0
    assert body["failed_embeddings"] == 0


@pytest.mark.asyncio
async def test_bulk_reindex_dry_run_does_not_write(client, db_session):
    await _ingest_mock_dataset(db_session)
    before = (await client.get("/api/v1/legal/knowledge/index-status")).json()

    response = await client.post("/api/v1/legal/knowledge/reindex", json={"dry_run": True})
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    # Already in the target namespace (same provider/model as ingestion used) —
    # nothing new to (dry-run) reindex.
    assert body["already_current"] == before["total_chunks"]
    assert body["would_reindex"] == 0

    after = (await client.get("/api/v1/legal/knowledge/index-status")).json()
    assert after == before


@pytest.mark.asyncio
async def test_search_debug_endpoint_returns_full_diagnostics(client, db_session):
    await _ingest_mock_dataset(db_session)

    response = await client.post("/api/v1/legal/search/debug", json={"query": "надлежащим образом", "top_k": 5})
    assert response.status_code == 200
    body = response.json()

    assert body["query"] == "надлежащим образом"
    assert isinstance(body["keyword_results"], list) and len(body["keyword_results"]) > 0
    assert isinstance(body["vector_results"], list)
    assert isinstance(body["hybrid_results"], list) and len(body["hybrid_results"]) > 0
    assert body["fusion"]["method"] == "reciprocal_rank_fusion"
    assert body["embedding"]["provider"] == "mock"
    assert body["embedding"]["namespace"]
    assert set(body["latency_ms"]) >= {"keyword_ms", "vector_ms", "fusion_ms", "reranker_ms", "citation_validation_ms", "total_ms"}
    assert isinstance(body["citation_validation"], list)
    # Diagnostics describe retrieval mechanics only — never a hidden-reasoning field.
    assert "chain_of_thought" not in body
    assert "reasoning" not in body


# --- Phase 6.5 §8: search/debug security/robustness against hostile input ---


@pytest.mark.asyncio
async def test_search_debug_handles_sql_injection_shaped_query_safely(client, db_session):
    await _ingest_mock_dataset(db_session)

    payload = {"query": "'; DROP TABLE embedding_chunks; --", "top_k": 5}
    response = await client.post("/api/v1/legal/search/debug", json=payload)
    assert response.status_code == 200  # SQLAlchemy parameterization neutralizes it; no 500

    # Table must still exist and be queryable afterward.
    still_alive = await client.get("/api/v1/legal/knowledge/index-status")
    assert still_alive.status_code == 200
    assert still_alive.json()["total_chunks"] > 0


@pytest.mark.asyncio
async def test_search_debug_handles_oversized_query_without_crashing(client, db_session):
    await _ingest_mock_dataset(db_session)

    huge_query = "надлежащим образом " * 5000  # ~100KB of repeated text
    response = await client.post("/api/v1/legal/search/debug", json={"query": huge_query, "top_k": 5})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_debug_handles_empty_query_string(client, db_session):
    await _ingest_mock_dataset(db_session)

    response = await client.post("/api/v1/legal/search/debug", json={"query": "", "top_k": 5})
    assert response.status_code == 200
    assert response.json()["keyword_results"] == []


@pytest.mark.asyncio
async def test_search_debug_rejects_malformed_effective_at(client, db_session):
    await _ingest_mock_dataset(db_session)

    response = await client.post(
        "/api/v1/legal/search/debug", json={"query": "test", "effective_at": "not-a-date", "top_k": 5}
    )
    assert response.status_code == 422  # Pydantic validation error, not a 500


@pytest.mark.asyncio
async def test_search_debug_requires_admin_role(client, app, db_session):
    """Confirms the route is actually gated by require_role(ADMIN), not just
    documented as such — flips the dev-stub identity to a non-admin role and
    checks the dependency rejects it. Must override on the same `app`
    instance the `client` fixture's ASGITransport wraps (the `app` fixture
    builds a fresh `create_app()` per test — importing the module-level
    `app.main.app` singleton would silently mutate a different, unused app).
    """
    import uuid

    from app.models.organization import RoleName
    from app.security.deps import CurrentUser, get_current_user

    async def viewer_identity():
        return CurrentUser(user_id=uuid.uuid4(), organization_id=uuid.uuid4(), role=RoleName.VIEWER)

    app.dependency_overrides[get_current_user] = viewer_identity
    try:
        response = await client.post("/api/v1/legal/search/debug", json={"query": "test", "top_k": 5})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_search_debug_never_leaks_tenant_documents(client, db_session):
    """search/debug queries the public Legal Knowledge Base only — it has
    no code path into tenant tables (Contract/Case), so a tenant's private
    document text can never appear in its results (Phase 6.5 brief §8/§9).
    """
    await _ingest_mock_dataset(db_session)

    response = await client.post(
        "/api/v1/legal/search/debug", json={"query": "надлежащим образом", "top_k": 20}
    )
    assert response.status_code == 200
    body = response.json()
    all_results = body["keyword_results"] + body["vector_results"] + body["hybrid_results"]
    for result in all_results:
        # Every candidate must trace back to the public KB, never a workspace-scoped row.
        assert "workspace_id" not in result["metadata"]


@pytest.mark.asyncio
async def test_citation_verify_endpoint_verified(client, db_session):
    await _ingest_mock_dataset(db_session)

    response = await client.post("/api/v1/legal/citations/verify", json={"citation_text": "ГК РФ, статья 314"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("mock", "verified")  # mock dataset -> MOCK, per LEGAL-RAG.md §4


@pytest.mark.asyncio
async def test_citation_verify_endpoint_unparseable_text(client, db_session):
    response = await client.post("/api/v1/legal/citations/verify", json={"citation_text": "not a citation at all"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_citation_verify_endpoint_unknown_article(client, db_session):
    response = await client.post("/api/v1/legal/citations/verify", json={"citation_text": "ГК РФ, статья 99999"})
    assert response.status_code == 200
    assert response.json()["status"] == "unverified"
