"""Knowledge base / verification — LEGAL-API.md §Knowledge base / verification,
plus the `/knowledge/*` admin namespace added in Phase 2 (brief §35 — see
revision note in LEGAL-API.md).
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_session
from app.domains.legal_knowledge.ingestion.mock_adapter import MockSourceNormalizer, MockSourceParser, MockSourceValidator
from app.domains.legal_knowledge.ingestion.pipeline import IngestionPipeline
from app.models.contracts import Contract
from app.models.embedding_chunk import EmbeddingChunk
from app.models.legal_knowledge import LegalSource
from app.models.matters import Case, Document, LegalResearchReport
from app.models.organization import RoleName
from app.rag.embeddings.base import embedding_namespace, get_embedding_provider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer, ReindexLimitExceeded
from app.rag.reranking.base import MockReranker
from app.rag.retrieval.base import RetrievalQuery, Retriever
from app.rag.retrieval.factory import build_hybrid_retriever
from app.rag.retrieval.hybrid_retriever import _reciprocal_rank_fusion
from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever
from app.rag.retrieval.vector_retriever import PgVectorRetriever
from app.rag.validation.citation_validator import CitationDraft, CitationValidator
from app.security.deps import get_current_user, get_workspace_id, require_role
from app.sources.mock.mock_source import MockLegalDataSource

router = APIRouter(tags=["knowledge"])

_VALID_MODES = {"semantic", "exact", "hybrid"}

# Only the mock source has a working SourceAdapter+Parser triple today
# (LEGAL-SOURCES.md §14 investigation — real sources are adapter-boundary-only).
_SOURCE_ADAPTERS = {
    "mock": (MockLegalDataSource(), MockSourceParser(), MockSourceNormalizer(), MockSourceValidator()),
}


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    mode: str = Query("hybrid"),
    jurisdiction: str = Query("RU"),
    effective_at: date | None = Query(None),
    document_type: str | None = Query(None),
    article: str | None = Query(None),
    top_k: int = Query(10, ge=1, le=50),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if mode not in _VALID_MODES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"mode must be one of {sorted(_VALID_MODES)}")

    filters = {k: v for k, v in {"document_type": document_type, "article": article}.items() if v}
    query = RetrievalQuery(
        text=q, jurisdiction=jurisdiction, event_date=effective_at.isoformat() if effective_at else None,
        filters=filters, top_k=top_k,
    )

    retriever: Retriever
    if mode == "hybrid":
        retriever = build_hybrid_retriever(session)
    elif mode == "exact":
        from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever

        retriever = PostgresKeywordRetriever(session)
    else:
        from app.rag.retrieval.vector_retriever import PgVectorRetriever

        retriever = PgVectorRetriever(session, get_embedding_provider())

    results = await retriever.retrieve(query)

    return {
        "query": q,
        "results": [
            {
                "document_id": r.document_id,
                "title": r.title,
                "snippet": r.snippet,
                "score": r.score,
                "retrieval_method": r.metadata.get("matched_by", [r.retrieval_mode]),
                "metadata": r.metadata,
            }
            for r in results
        ],
        "total": len(results),
        "retrieval": {"keyword": mode in ("hybrid", "exact"), "vector": mode in ("hybrid", "semantic"), "reranking": mode == "hybrid"},
    }


@router.get("/search/global")
async def search_global(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Tenant + public-knowledge search across product surfaces (Phase 8 brief
    §12) — separate from `/search` (public Legal Knowledge Base only) because
    tenant data (Case/Contract/Document/LegalResearchReport) must never be
    blended into that endpoint's response without an explicit type label and
    workspace scope. Each result carries `type` so the frontend never guesses.
    """
    like = f"%{q}%"

    case_rows = (
        await session.execute(
            select(Case).where(Case.workspace_id == workspace_id, Case.title.ilike(like)).limit(limit)
        )
    ).scalars().all()
    contract_rows = (
        await session.execute(
            select(Contract).where(Contract.workspace_id == workspace_id, Contract.title.ilike(like)).limit(limit)
        )
    ).scalars().all()
    document_rows = (
        await session.execute(
            select(Document).where(Document.workspace_id == workspace_id, Document.title.ilike(like)).limit(limit)
        )
    ).scalars().all()
    research_rows = (
        await session.execute(
            select(LegalResearchReport)
            .where(LegalResearchReport.workspace_id == workspace_id, LegalResearchReport.question.ilike(like))
            .limit(limit)
        )
    ).scalars().all()

    law_query = RetrievalQuery(text=q, jurisdiction="RU", top_k=limit)
    law_results = await build_hybrid_retriever(session).retrieve(law_query)

    return {
        "query": q,
        "results": (
            [{"type": "CASE", "id": str(c.id), "title": c.title, "subtitle": c.status.value} for c in case_rows]
            + [
                {"type": "CONTRACT", "id": str(c.id), "title": c.title, "subtitle": c.status.value}
                for c in contract_rows
            ]
            + [
                {"type": "DOCUMENT", "id": str(d.id), "title": d.title, "subtitle": d.document_type.value}
                for d in document_rows
            ]
            + [
                {"type": "RESEARCH", "id": str(r.id), "title": r.question, "subtitle": r.confidence}
                for r in research_rows
            ]
            + [{"type": "LAW", "id": r.document_id, "title": r.title, "subtitle": r.snippet} for r in law_results[:limit]]
        ),
    }


class SearchDebugRequest(BaseModel):
    query: str
    jurisdiction: str = "RU"
    effective_at: date | None = None
    top_k: int = 10


@router.post("/search/debug")
async def search_debug(
    body: SearchDebugRequest,
    user=Depends(require_role(RoleName.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Retrieval diagnostics — Phase 6 brief §12. Admin/Owner only: this
    exposes retrieval *mechanics* (which candidates each leg found, fusion
    scores, timings, embedding identity) for debugging why a query returned
    what it did. It never exposes chain-of-thought or hidden LLM reasoning —
    there is none here, this endpoint doesn't call an LLM at all.
    """
    embedding_provider = get_embedding_provider()
    rquery = RetrievalQuery(
        text=body.query, jurisdiction=body.jurisdiction,
        event_date=body.effective_at.isoformat() if body.effective_at else None, top_k=body.top_k,
    )
    wide_query = RetrievalQuery(
        text=rquery.text, jurisdiction=rquery.jurisdiction, event_date=rquery.event_date, top_k=max(body.top_k * 3, 30),
    )

    t0 = time.perf_counter()
    keyword_results = await PostgresKeywordRetriever(session).retrieve(wide_query)
    keyword_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    vector_results = await PgVectorRetriever(session, embedding_provider).retrieve(wide_query)
    vector_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    fused = _reciprocal_rank_fusion(keyword_results, vector_results)
    fusion_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    reranked = await MockReranker().rerank(rquery, fused)
    rerank_ms = (time.perf_counter() - t0) * 1000
    hybrid_results = reranked[: body.top_k]

    t0 = time.perf_counter()
    citation_checks = []
    validator = CitationValidator(session)
    for r in hybrid_results:
        law_short_name = r.metadata.get("law_short_name")
        article_number = r.metadata.get("article_number")
        if not (law_short_name and article_number):
            continue
        check = await validator.validate(
            CitationDraft(law_short_name=law_short_name, article_number=article_number, quoted_fragment=None, event_date=body.effective_at)
        )
        citation_checks.append(
            {"document_id": r.document_id, "law_short_name": law_short_name, "article_number": article_number, "status": check.status.value}
        )
    citation_ms = (time.perf_counter() - t0) * 1000

    def _candidate(r):
        return {
            "document_id": r.document_id, "title": r.title, "score": r.score,
            "retrieval_mode": r.retrieval_mode, "metadata": r.metadata,
        }

    return {
        "query": body.query,
        "effective_at": body.effective_at.isoformat() if body.effective_at else None,
        "keyword_results": [_candidate(r) for r in keyword_results[: body.top_k]],
        "vector_results": [_candidate(r) for r in vector_results[: body.top_k]],
        "hybrid_results": [_candidate(r) for r in hybrid_results],
        "fusion": {"method": "reciprocal_rank_fusion", "candidate_count": len(fused)},
        "filters": {"jurisdiction": body.jurisdiction, "top_k": body.top_k},
        "embedding": {
            "provider": embedding_provider.provider_name, "model": embedding_provider.model_name,
            "namespace": embedding_namespace(embedding_provider),
        },
        "latency_ms": {
            "keyword_ms": round(keyword_ms, 2), "vector_ms": round(vector_ms, 2), "fusion_ms": round(fusion_ms, 2),
            "reranker_ms": round(rerank_ms, 2), "citation_validation_ms": round(citation_ms, 2),
            "total_ms": round(keyword_ms + vector_ms + fusion_ms + rerank_ms + citation_ms, 2),
        },
        "citation_validation": citation_checks,
    }


# --- /knowledge/* admin namespace (brief §35) ---


@router.get("/knowledge/sources")
async def list_knowledge_sources(
    user=Depends(require_role(RoleName.ADMIN)), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    result = await session.execute(select(LegalSource))
    return [
        {
            "id": str(s.id), "name": s.name, "type": s.type.value, "is_official": s.is_official, "is_mock": s.is_mock,
            "status": s.status, "last_sync_at": s.last_sync_at, "last_successful_sync_at": s.last_successful_sync_at,
            "last_error": s.last_error,
        }
        for s in result.scalars().all()
    ]


@router.post("/knowledge/sources/{source_id}/sync")
async def sync_knowledge_source(
    source_id: uuid.UUID, user=Depends(require_role(RoleName.ADMIN)), session: AsyncSession = Depends(get_session)
) -> dict:
    legal_source = await session.get(LegalSource, source_id)
    if legal_source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Legal source not found")

    adapter = _SOURCE_ADAPTERS.get(legal_source.provider or "")
    if adapter is None:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"No working SourceAdapter for provider={legal_source.provider!r} yet — see LEGAL-SOURCES.md §14.",
        )
    source_obj, parser, normalizer, validator = adapter

    indexer = LegalChunkIndexer(session, get_embedding_provider())
    pipeline = IngestionPipeline(session, source_obj, parser, normalizer, validator, indexer=indexer)

    try:
        results = await pipeline.ingest_source(legal_source)
        legal_source.last_sync_at = date.today().isoformat()
        legal_source.last_successful_sync_at = legal_source.last_sync_at
        legal_source.last_error = None
    except Exception as exc:  # noqa: BLE001 — surfaced to admin via last_error, not swallowed
        legal_source.last_sync_at = date.today().isoformat()
        legal_source.last_error = str(exc)
        await session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Sync failed: {exc}") from exc

    await session.commit()
    return {
        "source_id": str(source_id),
        "ingested": sum(1 for r in results if not r.skipped),
        "skipped": sum(1 for r in results if r.skipped),
    }


@router.get("/knowledge/documents")
async def list_knowledge_documents(
    document_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user=Depends(require_role(RoleName.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    stmt = select(EmbeddingChunk).limit(limit)
    if document_type:
        stmt = stmt.where(EmbeddingChunk.document_type == document_type)
    result = await session.execute(stmt)
    return [
        {
            "chunk_id": str(c.id), "chunk_type": c.chunk_type, "document_type": c.document_type,
            "article_number": c.article_number, "is_mock": c.is_mock, "embedding_model": c.embedding_model,
        }
        for c in result.scalars().all()
    ]


@router.post("/knowledge/documents/{chunk_id}/reindex")
async def reindex_knowledge_document(
    chunk_id: uuid.UUID, user=Depends(require_role(RoleName.ADMIN)), session: AsyncSession = Depends(get_session)
) -> dict:
    existing = await session.get(EmbeddingChunk, chunk_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Indexed chunk not found")

    indexer = LegalChunkIndexer(session, get_embedding_provider())
    reindexed = await indexer.reindex_by_ids(existing.chunk_type, existing.chunk_id)
    if reindexed is None:  # pragma: no cover — chunk existed a line above; only reachable on a concurrent delete
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chunk was deleted concurrently during reindex")
    await session.commit()
    return {"chunk_id": str(reindexed.id), "reindexed": True}


@router.get("/knowledge/index-status")
async def knowledge_index_status(
    user=Depends(require_role(RoleName.ADMIN)), session: AsyncSession = Depends(get_session)
) -> dict:
    total = await session.execute(select(func.count()).select_from(EmbeddingChunk))
    by_type = await session.execute(select(EmbeddingChunk.document_type, func.count()).group_by(EmbeddingChunk.document_type))
    mock_count = await session.execute(select(func.count()).select_from(EmbeddingChunk).where(EmbeddingChunk.is_mock.is_(True)))
    by_namespace = await session.execute(
        select(EmbeddingChunk.embedding_namespace, func.count()).group_by(EmbeddingChunk.embedding_namespace)
    )

    active_provider = get_embedding_provider()
    active_namespace = embedding_namespace(active_provider)
    active_namespace_count = await session.execute(
        select(func.count()).select_from(EmbeddingChunk).where(EmbeddingChunk.embedding_namespace == active_namespace)
    )

    total_chunks = total.scalar_one()
    return {
        "total_chunks": total_chunks,
        "by_document_type": {doc_type: count for doc_type, count in by_type.all()},
        "mock_chunks": mock_count.scalar_one(),
        "embedding_chunks": total_chunks,
        "pending_embeddings": 0,  # embed() is synchronous-in-request today — nothing is ever left half-written (brief §54)
        "failed_embeddings": 0,
        "active_embedding": {
            "provider": active_provider.provider_name, "model": active_provider.model_name,
            "dimensions": active_provider.dimensions, "namespace": active_namespace,
            "chunks_in_active_namespace": active_namespace_count.scalar_one(),
        },
        "by_namespace": {ns: count for ns, count in by_namespace.all()},
    }


class ReindexRequest(BaseModel):
    source_id: uuid.UUID | None = None
    dry_run: bool = False


@router.post("/knowledge/reindex")
async def reindex_knowledge_base(
    body: ReindexRequest, user=Depends(require_role(RoleName.ADMIN)), session: AsyncSession = Depends(get_session)
) -> dict:
    """Bulk re-embed into whatever provider/model EMBEDDING_PROVIDER/
    EMBEDDING_MODEL currently resolve to (Phase 6 brief §4) — "activating"
    a namespace is changing that configuration; this endpoint's job is only
    to populate it. Old namespaces are never touched, so this is always
    safe to run again or to leave half-migrated. `ready_to_activate` in the
    response is the Phase 6.5 §6 gate: only true once every chunk that
    exists elsewhere has a same-namespace counterpart with zero failures —
    check it before flipping EMBEDDING_PROVIDER/EMBEDDING_MODEL in config.
    """
    indexer = LegalChunkIndexer(session, get_embedding_provider())
    settings = get_settings()
    try:
        report = await indexer.reindex_all(
            source_id=body.source_id, dry_run=body.dry_run, max_documents=settings.embedding_max_documents_per_reindex
        )
    except ReindexLimitExceeded as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    if not body.dry_run:
        await session.commit()
    return {
        "target_namespace": report.target_namespace,
        "total": report.total,
        "reindexed": report.reindexed,
        "already_current": report.already_current,
        "would_reindex": report.would_reindex,
        "failed": report.failed,
        "errors": report.errors,
        "dry_run": body.dry_run,
        "ready_to_activate": report.ready_to_activate,
    }


# --- Citations (LEGAL-API.md §Knowledge base / verification) ---


@router.get("/citations/{citation_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def get_citation(citation_id: uuid.UUID, user=Depends(get_current_user)) -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Persisted Citation-row detail lookup is Phase 3 work.")


class VerifyCitationRequest(BaseModel):
    citation_text: str
    effective_at: date | None = None


_CITATION_PATTERN = re.compile(r"(?P<law>[^,]+?),?\s*ст(?:атья|\.)?\s*(?P<article>\d+)", re.IGNORECASE)


@router.post("/citations/verify")
async def verify_citation(
    body: VerifyCitationRequest, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    match = _CITATION_PATTERN.search(body.citation_text)
    if not match:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Could not parse a law/article reference from citation_text (expected e.g. 'ГК РФ, статья 309').",
        )

    validator = CitationValidator(session)
    check = await validator.validate(
        CitationDraft(
            law_short_name=match.group("law").strip(),
            article_number=match.group("article"),
            quoted_fragment=None,
            event_date=body.effective_at,
        )
    )
    return {
        "citation_text": body.citation_text,
        "status": check.status.value,
        "reason": check.reason,
        "law_version_id": check.law_version_id,
        "source_id": check.source_id,
    }


@router.get("/risks")
async def list_risks(
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
) -> list:
    # LegalRisk model + repository exist (app/models/matters.py); a dedicated
    # WorkspaceScopedRepository for it is added alongside Risk Engine work (Phase 3).
    return []


@router.get("/evidence")
async def list_evidence(
    case_id: uuid.UUID | None = None,
    user=Depends(get_current_user),
) -> list:
    return []
