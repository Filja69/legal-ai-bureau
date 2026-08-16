"""Shared metadata-filter application over EmbeddingChunk (brief §25).

Both the keyword and vector retrievers apply the exact same filter set so a
hybrid merge never has to reconcile "matched vector filters but not keyword
filters" — filtering happens once, per leg, from one function.
"""
from __future__ import annotations

from sqlalchemy import Select

from app.models.embedding_chunk import EmbeddingChunk
from app.rag.retrieval.base import RetrievalQuery


def apply_filters(stmt: Select, query: RetrievalQuery) -> Select:
    stmt = stmt.where(EmbeddingChunk.jurisdiction == query.jurisdiction)

    filters = query.filters
    if document_type := filters.get("document_type"):
        stmt = stmt.where(EmbeddingChunk.document_type == document_type)
    if law_id := filters.get("law_id"):
        stmt = stmt.where(EmbeddingChunk.law_id == law_id)
    if article := filters.get("article"):
        stmt = stmt.where(EmbeddingChunk.article_number == article)
    if source_id := filters.get("source_id"):
        stmt = stmt.where(EmbeddingChunk.source_id == source_id)
    if court_decision_id := filters.get("court_decision_id"):
        stmt = stmt.where(EmbeddingChunk.court_decision_id == court_decision_id)
    if date_from := filters.get("date_from"):
        stmt = stmt.where((EmbeddingChunk.effective_to.is_(None)) | (EmbeddingChunk.effective_to >= date_from))
    if date_to := filters.get("date_to"):
        stmt = stmt.where(EmbeddingChunk.effective_from <= date_to)

    # effective_at (LEGAL-RAG.md §1 Temporal Retrieval): only chunks whose
    # validity window actually contains this date — the same [)-semantics
    # as TemporalLawResolver, applied at the chunk level. Only meaningful for
    # law_article chunks; court_decision chunks have no effective_from/to and
    # pass through untouched (nothing to exclude them on).
    if query.event_date:
        stmt = stmt.where(
            (EmbeddingChunk.effective_from.is_(None)) | (EmbeddingChunk.effective_from <= query.event_date)
        ).where((EmbeddingChunk.effective_to.is_(None)) | (EmbeddingChunk.effective_to > query.event_date))

    return stmt
