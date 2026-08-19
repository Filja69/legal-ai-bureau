"""Batch (JSONL-shaped) curated import — starter-KB task.

"Whole-batch dry-run first, reject entire batch if any line fails,
idempotent, preserve trust semantics, index for retrieval" — each proven
directly against CuratedImportService.preview_batch()/import_batch(), the
same service the CLI's --batch flag drives. Synthetic fixtures only
(rule 14 carries over) — no real legal text.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.domains.legal_knowledge.curated_import import (
    CuratedImportInput,
    CuratedImportKind,
    CuratedImportService,
)
from app.models.embedding_chunk import EmbeddingChunk
from app.models.legal_knowledge import Law, LawVersion, LegalSource
from app.models.source_document import SourceDocument
from app.rag.embeddings.base import MockEmbeddingProvider
from app.rag.indexing.chunk_indexer import LegalChunkIndexer
from app.rag.retrieval.base import RetrievalQuery
from app.rag.retrieval.keyword_retriever import PostgresKeywordRetriever
from app.rag.validation.citation_validator import CitationDraft, CitationStatus, CitationValidator

pytestmark = pytest.mark.asyncio

_TEXTS = {
    "309": "TEST FIXTURE — обязательства должны исполняться надлежащим образом.",
    "310": "TEST FIXTURE — односторонний отказ от исполнения обязательства не допускается.",
    "333": "TEST FIXTURE — суд вправе уменьшить явно несоразмерную неустойку.",
}


def _line(article_number: str, **overrides) -> CuratedImportInput:
    defaults = dict(
        kind=CuratedImportKind.LAW_ARTICLE,
        source_url="https://pravo.gov.ru/test-fixture",
        confirmed_official_source=True,
        title=f"TEST FIXTURE Статья {article_number}",
        text=_TEXTS[article_number],
        law_short_name="TEST-GK",
        article_number=article_number,
        valid_from=date(2015, 6, 1),
        imported_by="test-operator",
    )
    defaults.update(overrides)
    return CuratedImportInput(**defaults)


def _clean_batch() -> list[CuratedImportInput]:
    return [_line("309"), _line("310"), _line("333")]


def _service(db_session) -> CuratedImportService:
    indexer = LegalChunkIndexer(db_session, MockEmbeddingProvider())
    return CuratedImportService(db_session, indexer=indexer)


async def test_batch_dry_run_writes_nothing(db_session):
    service = _service(db_session)
    outcomes = await service.preview_batch(_clean_batch())
    await db_session.flush()

    assert len(outcomes) == 3
    assert all(o.ok for o in outcomes)
    assert (await db_session.execute(select(LawVersion))).scalars().all() == []
    assert (await db_session.execute(select(LegalSource))).scalars().all() == []


async def test_batch_import_creates_all_records(db_session):
    service = _service(db_session)
    outcomes = await service.import_batch(_clean_batch())
    await db_session.commit()

    assert all(o.ok for o in outcomes)
    law_versions = (await db_session.execute(select(LawVersion))).scalars().all()
    assert {v.article_number for v in law_versions} == {"309", "310", "333"}
    # One shared Law row (same law_short_name across all three lines).
    laws = (await db_session.execute(select(Law))).scalars().all()
    assert len(laws) == 1
    assert laws[0].short_name == "TEST-GK"


async def test_batch_rejects_entire_batch_if_one_line_invalid(db_session):
    service = _service(db_session)
    broken_line = _line("310")
    broken_line.article_number = None
    bad_batch = [_line("309"), broken_line, _line("333")]

    outcomes = await service.import_batch(bad_batch)
    await db_session.commit()  # nothing to commit -- import_batch wrote nothing

    assert outcomes[0].ok is True
    assert outcomes[1].ok is False
    assert "article_number" in (outcomes[1].error or "")
    assert outcomes[2].ok is True
    # Whole batch rejected: NOT even the two valid lines were written.
    assert (await db_session.execute(select(LawVersion))).scalars().all() == []


async def test_batch_rejects_entire_batch_on_intra_batch_duplicate_identity(db_session):
    service = _service(db_session)
    colliding_batch = [_line("309"), _line("309", text=_TEXTS["309"] + " (a different copy)")]

    outcomes = await service.import_batch(colliding_batch)
    await db_session.commit()

    assert outcomes[0].ok is True
    assert outcomes[1].ok is False
    assert "duplicate identity within this batch" in (outcomes[1].error or "")
    assert (await db_session.execute(select(LawVersion))).scalars().all() == []


async def test_batch_conflicting_with_existing_db_record_rejects_whole_batch(db_session):
    service = _service(db_session)
    await service.import_batch([_line("309")])
    await db_session.commit()

    # Re-import "309" with DIFFERENT text (real conflict) alongside a
    # brand-new "310" -- the whole batch must be rejected, including 310.
    outcomes = await service.import_batch([_line("309", text=_TEXTS["309"] + " CHANGED"), _line("310")])
    await db_session.commit()

    assert outcomes[0].ok is False
    assert "conflict" in (outcomes[0].error or "").lower()
    law_versions = (await db_session.execute(select(LawVersion))).scalars().all()
    assert {v.article_number for v in law_versions} == {"309"}  # 310 never got written


async def test_batch_reimport_is_idempotent(db_session):
    service = _service(db_session)
    first = await service.import_batch(_clean_batch())
    await db_session.commit()
    first_ids = {o.result.law_version_id for o in first if o.result and o.result.law_version_id}
    assert len(first_ids) == 3

    second = await service.import_batch(_clean_batch())
    await db_session.commit()

    assert all(o.ok for o in second)
    for outcome in second:
        assert outcome.result is not None
        assert outcome.result.skipped is True  # every line recognized as an already-imported duplicate, not re-created

    law_versions = (await db_session.execute(select(LawVersion))).scalars().all()
    assert {v.id for v in law_versions} == first_ids  # exactly the three from the first run -- no duplicates created


async def test_batch_preserves_trust_semantics_unconfirmed_not_verified(db_session):
    service = _service(db_session)
    outcomes = await service.import_batch([_line("309", confirmed_official_source=False)])
    await db_session.commit()
    assert outcomes[0].ok is True

    source_document = await db_session.get(SourceDocument, outcomes[0].result.source_document_id)
    legal_source = await db_session.get(LegalSource, source_document.source_id)
    assert legal_source.is_official is False

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(law_short_name="TEST-GK", article_number="309", quoted_fragment=None, event_date=date(2020, 1, 1))
    )
    assert check.status == CitationStatus.UNVERIFIED  # not VERIFIED, no bypass


async def test_batch_preserves_trust_semantics_confirmed_reaches_verified(db_session):
    service = _service(db_session)
    await service.import_batch([_line("309", confirmed_official_source=True)])
    await db_session.commit()

    validator = CitationValidator(db_session)
    check = await validator.validate(
        CitationDraft(
            law_short_name="TEST-GK", article_number="309", quoted_fragment=_TEXTS["309"], event_date=date(2020, 1, 1)
        )
    )
    assert check.status == CitationStatus.VERIFIED


async def test_batch_indexes_embedding_chunks_for_every_line(db_session):
    service = _service(db_session)
    outcomes = await service.import_batch(_clean_batch())
    await db_session.commit()

    for outcome in outcomes:
        assert outcome.result is not None
        assert outcome.result.embedding_indexed is True
        chunks = (
            await db_session.execute(
                select(EmbeddingChunk).where(
                    EmbeddingChunk.chunk_type == "law_version", EmbeddingChunk.chunk_id == outcome.result.law_version_id
                )
            )
        ).scalars().all()
        assert len(chunks) == 1
        assert chunks[0].is_mock is False


async def test_batch_indexed_articles_are_actually_retrievable(db_session):
    service = _service(db_session)
    await service.import_batch(_clean_batch())
    await db_session.commit()

    retriever = PostgresKeywordRetriever(db_session)
    results = await retriever.retrieve(RetrievalQuery(text="уменьшить явно несоразмерную неустойку", top_k=10))

    assert any(r.metadata.get("article_number") == "333" for r in results)
