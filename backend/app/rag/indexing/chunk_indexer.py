"""LegalChunkIndexer — writes EmbeddingChunk rows (brief §21-23, LEGAL-RAG.md §1).

Implements app.domains.legal_knowledge.ingestion.protocols.LegalIndexer —
the ingestion pipeline's final stage. Also exposes `reindex` directly, for
the admin `/knowledge/documents/{id}/reindex` endpoint (brief §35) without
re-running the whole ingestion pipeline.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_chunk import EmbeddingChunk
from app.rag.embeddings.base import EmbeddingProvider, embedding_namespace


@dataclass
class ReindexReport:
    target_namespace: str
    total: int
    reindexed: int = 0
    already_current: int = 0
    would_reindex: int = 0  # dry_run only
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ready_to_activate(self) -> bool:
        # Phase 6.5 brief §6 — a namespace is only safe to switch
        # EMBEDDING_PROVIDER/EMBEDDING_MODEL to once EVERY chunk that exists
        # elsewhere has a counterpart here, with zero failures. Partial
        # coverage must never look "close enough" to activate.
        return self.failed == 0 and (self.reindexed + self.already_current) == self.total


class ReindexLimitExceeded(RuntimeError):
    """Raised instead of running an oversized reindex (Phase 6.5 brief §3) —
    fail closed on a bulk operation that could otherwise generate an
    unbounded real-provider bill, rather than silently proceeding."""


class LegalChunkIndexer:
    def __init__(self, session: AsyncSession, embedding_provider: EmbeddingProvider) -> None:
        self._session = session
        self._embedding_provider = embedding_provider

    async def index_chunk(self, chunk_type: str, chunk_id: uuid.UUID, text: str, metadata: dict) -> None:
        namespace = embedding_namespace(self._embedding_provider)
        # Upsert semantics *within this namespace only* (Phase 6 brief §4):
        # re-embedding into the SAME namespace replaces the prior row for
        # that chunk, but embedding into a DIFFERENT (e.g. new provider's)
        # namespace never touches other namespaces' rows — old embeddings
        # are never auto-deleted, so a reindex is always rollback-safe until
        # someone explicitly purges the old namespace.
        await self._session.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.chunk_type == chunk_type,
                EmbeddingChunk.chunk_id == chunk_id,
                EmbeddingChunk.embedding_namespace == namespace,
            )
        )

        [embedding] = await self._embedding_provider.embed([text])

        chunk = EmbeddingChunk(
            chunk_type=chunk_type,
            chunk_id=chunk_id,
            chunk_text=text,
            chunk_index=0,
            token_count=len(text.split()),
            embedding=embedding,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimension=self._embedding_provider.dimensions,
            embedding_provider=self._embedding_provider.provider_name,
            embedding_model_version=self._embedding_provider.model_version,
            embedding_namespace=namespace,
            jurisdiction=metadata.get("jurisdiction"),
            document_type=metadata.get("document_type"),
            law_id=_maybe_uuid(metadata.get("law_id")),
            law_version_id=_maybe_uuid(metadata.get("law_version_id")),
            article_number=metadata.get("article_number"),
            court_decision_id=_maybe_uuid(metadata.get("court_decision_id")),
            effective_from=metadata.get("effective_from"),
            effective_to=metadata.get("effective_to"),
            source_id=_maybe_uuid(metadata.get("source_id")),
            is_mock=bool(metadata.get("is_mock", False)),
            chunk_metadata=metadata,
        )
        self._session.add(chunk)
        await self._session.flush()

    async def reindex_by_ids(self, chunk_type: str, chunk_id: uuid.UUID) -> EmbeddingChunk | None:
        # Read the source text from *any* existing namespace for this chunk
        # (they all carry the same chunk_text/metadata by construction) —
        # then write into whichever namespace this indexer's provider owns.
        result = await self._session.execute(
            select(EmbeddingChunk).where(EmbeddingChunk.chunk_type == chunk_type, EmbeddingChunk.chunk_id == chunk_id).limit(1)
        )
        existing = result.scalars().first()
        if existing is None:
            return None
        await self.index_chunk(chunk_type, chunk_id, existing.chunk_text, existing.chunk_metadata)
        namespace = embedding_namespace(self._embedding_provider)
        result = await self._session.execute(
            select(EmbeddingChunk).where(
                EmbeddingChunk.chunk_type == chunk_type,
                EmbeddingChunk.chunk_id == chunk_id,
                EmbeddingChunk.embedding_namespace == namespace,
            )
        )
        return result.scalars().first()

    async def reindex_all(
        self, *, source_id: uuid.UUID | None = None, dry_run: bool = False, max_documents: int | None = None
    ) -> ReindexReport:
        """Re-embed every currently-indexed chunk into this indexer's
        provider's namespace (Phase 6 brief §4 "old namespace -> new
        namespace -> reindex -> benchmark -> switch"). Reads distinct
        (chunk_type, chunk_id) pairs from whatever namespace already has
        them — never re-runs the ingestion pipeline, purely a re-embed.

        `max_documents` (Phase 6.5 brief §3) is a hard ceiling: exceeding it
        raises `ReindexLimitExceeded` instead of running — even in
        `dry_run` mode, since a dry run against an unbounded corpus is still
        an unbounded DB scan. Pass `None` to skip the check entirely.
        """
        stmt = select(EmbeddingChunk.chunk_type, EmbeddingChunk.chunk_id).distinct()
        if source_id is not None:
            stmt = stmt.where(EmbeddingChunk.source_id == source_id)
        pairs = (await self._session.execute(stmt)).all()

        if max_documents is not None and len(pairs) > max_documents:
            raise ReindexLimitExceeded(
                f"reindex_all would touch {len(pairs)} documents, exceeding the configured limit of "
                f"{max_documents} (EMBEDDING_MAX_DOCUMENTS_PER_REINDEX). Narrow with source_id, or raise "
                "the limit deliberately if this is genuinely intended."
            )

        target_namespace = embedding_namespace(self._embedding_provider)
        already_done = (
            await self._session.execute(
                select(EmbeddingChunk.chunk_type, EmbeddingChunk.chunk_id).where(
                    EmbeddingChunk.embedding_namespace == target_namespace
                )
            )
        ).all()
        already_done_set = set(already_done)

        report = ReindexReport(target_namespace=target_namespace, total=len(pairs))
        for chunk_type, chunk_id in pairs:
            if (chunk_type, chunk_id) in already_done_set:
                report.already_current += 1
                continue
            if dry_run:
                report.would_reindex += 1
                continue
            try:
                reindexed = await self.reindex_by_ids(chunk_type, chunk_id)
                if reindexed is None:
                    report.failed += 1
                else:
                    report.reindexed += 1
            except Exception as exc:  # noqa: BLE001 — recorded per-chunk, never aborts the whole batch silently
                report.failed += 1
                report.errors.append(f"{chunk_type}:{chunk_id}: {exc}")
        return report


def _maybe_uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(value) if value else None
