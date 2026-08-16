"""DocumentIndexer interface — ingestion pipeline's final step (LEGAL-SOURCES.md §6):
chunk -> embed -> write EmbeddingChunk + full-text index rows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class IndexResult:
    document_id: str
    chunks_indexed: int


class DocumentIndexer(Protocol):
    async def index(self, document_id: str, content: str) -> IndexResult: ...


class MockDocumentIndexer:
    """No-op indexer — records nothing, used until real chunking/embedding/storage lands (Phase 2)."""

    async def index(self, document_id: str, content: str) -> IndexResult:
        return IndexResult(document_id=document_id, chunks_indexed=0)
