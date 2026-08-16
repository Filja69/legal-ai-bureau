"""LegalChunkIndexer namespace isolation + bulk reindex (Phase 6 brief §4).

Old embeddings must never be silently deleted by a reindex into a different
namespace — this is what makes rollback possible. Real Postgres, no mocked
embedding math (MockEmbeddingProvider is deterministic and cheap enough to
run for real here).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.embedding_chunk import EmbeddingChunk
from app.rag.embeddings.base import MockEmbeddingProvider, embedding_namespace
from app.rag.indexing.chunk_indexer import LegalChunkIndexer, ReindexLimitExceeded


class _OtherMockProvider(MockEmbeddingProvider):
    """A second, distinct namespace standing in for a real second provider —
    same math as MockEmbeddingProvider, different declared model name, which
    is all embedding_namespace() needs to treat it as incompatible."""

    def __init__(self, dimensions: int | None = None) -> None:
        super().__init__(dimensions)
        self.model_name = "mock-embedding-v2"


@pytest.mark.asyncio
async def test_reindex_into_new_namespace_preserves_old_namespace_rows(db_session):
    chunk_id = uuid.uuid4()
    old_indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider(dimensions=1536))
    await old_indexer.index_chunk("law_version", chunk_id, "надлежащее исполнение обязательства", {"is_mock": True})
    await db_session.flush()

    new_indexer = LegalChunkIndexer(db_session, _OtherMockProvider(dimensions=1536))
    reindexed = await new_indexer.reindex_by_ids("law_version", chunk_id)
    assert reindexed is not None

    rows = (
        await db_session.execute(
            select(EmbeddingChunk).where(EmbeddingChunk.chunk_type == "law_version", EmbeddingChunk.chunk_id == chunk_id)
        )
    ).scalars().all()

    namespaces = {r.embedding_namespace for r in rows}
    assert len(rows) == 2, "old namespace row must survive a reindex into a new namespace"
    assert embedding_namespace(MockEmbeddingProvider(dimensions=1536)) in namespaces
    assert embedding_namespace(_OtherMockProvider(dimensions=1536)) in namespaces


@pytest.mark.asyncio
async def test_reindex_same_namespace_replaces_not_duplicates(db_session):
    chunk_id = uuid.uuid4()
    indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider(dimensions=1536))
    await indexer.index_chunk("law_version", chunk_id, "text v1", {"is_mock": True})
    await indexer.index_chunk("law_version", chunk_id, "text v1", {"is_mock": True})  # re-embed, same namespace
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(EmbeddingChunk).where(EmbeddingChunk.chunk_type == "law_version", EmbeddingChunk.chunk_id == chunk_id)
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reindex_all_reports_counts_and_is_idempotent(db_session):
    ids = [uuid.uuid4() for _ in range(3)]
    old_indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider(dimensions=1536))
    for i, chunk_id in enumerate(ids):
        await old_indexer.index_chunk("law_version", chunk_id, f"text {i}", {"is_mock": True})
    await db_session.flush()

    new_indexer = LegalChunkIndexer(db_session, _OtherMockProvider(dimensions=1536))

    dry_run_report = await new_indexer.reindex_all(dry_run=True)
    assert dry_run_report.would_reindex == 3
    assert dry_run_report.reindexed == 0

    report = await new_indexer.reindex_all()
    assert report.reindexed == 3
    assert report.failed == 0

    # Second run: everything already in the target namespace, so nothing to redo.
    report_2 = await new_indexer.reindex_all()
    assert report_2.already_current == 3
    assert report_2.reindexed == 0


@pytest.mark.asyncio
async def test_reindex_all_rejects_oversized_batch_before_running(db_session):
    ids = [uuid.uuid4() for _ in range(5)]
    old_indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider(dimensions=1536))
    for i, chunk_id in enumerate(ids):
        await old_indexer.index_chunk("law_version", chunk_id, f"text {i}", {"is_mock": True})
    await db_session.flush()

    new_indexer = LegalChunkIndexer(db_session, _OtherMockProvider(dimensions=1536))
    with pytest.raises(ReindexLimitExceeded):
        await new_indexer.reindex_all(max_documents=3)

    # Nothing should have been written into the new namespace — fail closed
    # means fail *before* any work starts, not abort halfway.
    target_namespace = embedding_namespace(_OtherMockProvider(dimensions=1536))
    rows = (
        await db_session.execute(select(EmbeddingChunk).where(EmbeddingChunk.embedding_namespace == target_namespace))
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_reindex_report_ready_to_activate_reflects_full_coverage(db_session):
    ids = [uuid.uuid4() for _ in range(3)]
    old_indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider(dimensions=1536))
    for i, chunk_id in enumerate(ids):
        await old_indexer.index_chunk("law_version", chunk_id, f"text {i}", {"is_mock": True})
    await db_session.flush()

    new_indexer = LegalChunkIndexer(db_session, _OtherMockProvider(dimensions=1536))

    dry_run = await new_indexer.reindex_all(dry_run=True)
    assert dry_run.ready_to_activate is False  # nothing has actually been written yet

    complete = await new_indexer.reindex_all()
    assert complete.ready_to_activate is True
    assert complete.reindexed + complete.already_current == complete.total


@pytest.mark.asyncio
async def test_reindex_report_not_ready_to_activate_when_partial(db_session):
    ids = [uuid.uuid4() for _ in range(2)]
    old_indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider(dimensions=1536))
    for i, chunk_id in enumerate(ids):
        await old_indexer.index_chunk("law_version", chunk_id, f"text {i}", {"is_mock": True})
    await db_session.flush()

    new_indexer = LegalChunkIndexer(db_session, _OtherMockProvider(dimensions=1536))
    # Manually reindex only one of the two chunks — simulates a run that was
    # interrupted partway through.
    await new_indexer.reindex_by_ids("law_version", ids[0])
    await db_session.flush()

    report = await new_indexer.reindex_all()  # second pass: 1 already_current, 1 reindexed now
    assert report.ready_to_activate is True  # this run completes it

    # But a report built from a genuinely partial state (failed > 0) must
    # never claim ready_to_activate — construct that state directly since
    # MockEmbeddingProvider never fails on its own.
    from app.rag.indexing.chunk_indexer import ReindexReport

    partial_report = ReindexReport(target_namespace="x", total=2, reindexed=1, failed=1)
    assert partial_report.ready_to_activate is False
