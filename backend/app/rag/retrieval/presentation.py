"""Shared EmbeddingChunk -> RetrievedCandidate presentation, used by both
keyword and vector retrievers so hybrid merge always sees identically-shaped
candidates regardless of which leg produced them.
"""
from __future__ import annotations

from app.models.embedding_chunk import EmbeddingChunk


def title_for(chunk: EmbeddingChunk) -> str:
    if chunk.document_type == "law_article":
        return f"ст. {chunk.article_number}" if chunk.article_number else "law article"
    return f"дело {chunk.chunk_metadata.get('case_number', chunk.chunk_id)}"


def metadata_for(chunk: EmbeddingChunk) -> dict:
    return {
        "chunk_type": chunk.chunk_type,
        "chunk_id": str(chunk.chunk_id),
        "law_id": str(chunk.law_id) if chunk.law_id else None,
        "law_version_id": str(chunk.law_version_id) if chunk.law_version_id else None,
        "law_short_name": chunk.chunk_metadata.get("law_short_name"),
        "article_number": chunk.article_number,
        "court_decision_id": str(chunk.court_decision_id) if chunk.court_decision_id else None,
        "case_number": chunk.chunk_metadata.get("case_number"),
        "effective_from": chunk.effective_from,
        "effective_to": chunk.effective_to,
        "source_id": str(chunk.source_id) if chunk.source_id else None,
        "is_mock": chunk.is_mock,
    }
