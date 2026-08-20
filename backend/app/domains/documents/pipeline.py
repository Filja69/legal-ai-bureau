"""DocumentIntelligenceEngine — Phase 9.2 brief §2. Orchestrates
EXTRACTION -> NORMALIZATION -> STRUCTURE DETECTION -> CHUNKING -> HASHING ->
EMBEDDING/INDEX, updating `Document.status` at every step so the caller
never sees a fake READY. Extraction/chunking modules stay single-purpose
(see their own module docstrings); this is the only place that writes to
the database or decides what a failure means for the document's status.
"""
from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.chunking.chunker import build_chunks, content_hash
from app.documents.extraction.base import ExtractionError, OcrRequiredError
from app.documents.extraction.registry import get_extractor
from app.models.matters import Document, DocumentChunk, DocumentStatus
from app.rag.embeddings.base import EmbeddingProvider, EmbeddingProviderError, embedding_namespace, get_embedding_provider

logger = structlog.get_logger(__name__)


class DocumentIntelligenceEngine:
    def __init__(self, session: AsyncSession, embedding_provider: EmbeddingProvider | None = None) -> None:
        self._session = session
        self._embedding_provider = embedding_provider or get_embedding_provider()

    async def process(self, document: Document, content: bytes, suffix: str) -> None:
        """Idempotent (brief §25/§26): safe to call again on the same
        document (e.g. after fixing a transient failure, or a genuine
        "Retry" action) — always deletes any chunks from a prior run before
        inserting the new set, and never leaves `status` in a stale state.
        """
        document.status = DocumentStatus.PROCESSING
        document.processing_error = None
        await self._session.flush()

        extractor = get_extractor(suffix)
        if extractor is None:
            document.status = DocumentStatus.UNSUPPORTED
            document.processing_error = f"No text extractor is available for {suffix!r} files."
            await self._session.flush()
            return

        try:
            extracted = await extractor.extract(content)
        except OcrRequiredError as exc:
            document.status = DocumentStatus.OCR_REQUIRED
            document.processing_error = str(exc)
            await self._session.flush()
            return
        except ExtractionError as exc:
            document.status = DocumentStatus.FAILED
            document.processing_error = f"{exc.code}: {exc}"
            await self._session.flush()
            return
        except Exception as exc:  # noqa: BLE001 — an extractor crashing must never crash the request
            document.status = DocumentStatus.FAILED
            document.processing_error = "Unexpected extraction failure."
            logger.error(
                "document_extraction_crashed", document_id=str(document.id), error_type=type(exc).__name__
            )
            await self._session.flush()
            return

        result = build_chunks(extracted)

        await self._session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))

        texts = [c.text for c in result.chunks]
        try:
            embeddings = await self._embedding_provider.embed(texts) if texts else []
        except EmbeddingProviderError as exc:
            # P0 production incident: this was previously unguarded — an
            # uncaught exception here left `document.status` stuck at
            # PROCESSING forever (no chunks/extracted_text/processed_at were
            # written yet at this point, so nothing to roll back) and, at
            # the HTTP layer, produced a response with no CORS headers (see
            # app/api/v1/documents.py's storage.put() handling for the full
            # Starlette-middleware-ordering explanation — same mechanism).
            # Same graceful-failure discipline as the extraction try/except
            # above: mark FAILED with a real reason, never crash the request.
            document.status = DocumentStatus.FAILED
            document.processing_error = "Не удалось создать поисковый индекс для документа."
            logger.error("document_embedding_failed", document_id=str(document.id), error_type=type(exc).__name__)
            await self._session.flush()
            return
        namespace = embedding_namespace(self._embedding_provider)

        for chunk, vector in zip(result.chunks, embeddings, strict=True):
            self._session.add(
                DocumentChunk(
                    workspace_id=document.workspace_id,
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section_path=chunk.section_path,
                    text=chunk.text,
                    content_hash=content_hash(chunk.text),
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    embedding=vector,
                    embedding_model=self._embedding_provider.model_name,
                    embedding_namespace=namespace,
                )
            )

        document.extracted_text = result.normalized_text
        document.status = DocumentStatus.READY
        # Naive UTC, matching this codebase's other DB-written timestamps
        # (app/domains/legal_knowledge/ingestion/pipeline.py) and the
        # `processed_at` column type (TIMESTAMP WITHOUT TIME ZONE) — a
        # tz-aware datetime here fails at the asyncpg driver level ("can't
        # subtract offset-naive and offset-aware datetimes"), a real bug
        # caught this session by the first `pytest` run against a live
        # Postgres (docs/PHASE-9-2-INTEGRATION-VERIFICATION.md).
        document.processed_at = datetime.utcnow()
        document.doc_metadata = {
            **document.doc_metadata,
            "extractor": extracted.extractor,
            "page_count": extracted.metadata.get("page_count"),
            "chunk_count": len(result.chunks),
            "used_structure_detection": result.used_structure,
            "warnings": result.warnings,
        }
        await self._session.flush()

        logger.info(
            "document_processed",
            document_id=str(document.id),
            workspace_id=str(document.workspace_id),
            chunk_count=len(result.chunks),
            extractor=extracted.extractor,
        )
