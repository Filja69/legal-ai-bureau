"""Documents — LEGAL-API.md §Documents. Phase 9.2: real upload security
validation, text extraction (PDF/DOCX/TXT/XLSX), tenant-scoped chunking +
indexing, evidence-gated Q&A, and provenance-tagged analysis. OCR is
explicitly out of scope (brief §4) — a scanned PDF honestly reports
`ocr_required`, never a fabricated extraction.
"""
from __future__ import annotations

import hashlib
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_session
from app.documents.storage.base import DocumentStorageConfigError, DocumentStorageError, get_document_storage
from app.documents.validation import DocumentValidationError, validate_upload
from app.domains.documents.analysis import analyze_document
from app.domains.documents.pipeline import DocumentIntelligenceEngine
from app.domains.documents.qa import ask_documents
from app.models.matters import Document, DocumentChunk, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    DocumentAnalyzeResponse,
    DocumentAskRequest,
    DocumentAskResponse,
    DocumentCitationOut,
    DocumentOut,
    ExtractedFactOut,
)
from app.security.deps import get_current_user, get_workspace_id

router = APIRouter(tags=["documents"])
logger = structlog.get_logger(__name__)

_READ_CHUNK_BYTES = 1024 * 1024  # 1 MB — read incrementally so an oversized upload is
# rejected without ever buffering the full body in memory (Phase 9 audit §15).


async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _get_ready_document_or_409(session: AsyncSession, workspace_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = await DocumentRepository(session, workspace_id).get(document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    if document.status != DocumentStatus.READY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Document is not ready (status={document.status.value}) — {document.processing_error or 'processing has not completed'}",
        )
    return document


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Document]:
    return await DocumentRepository(session, workspace_id).list()


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Document:
    content = await _read_bounded(file, get_settings().max_upload_size_bytes)

    try:
        validated = validate_upload(content, file.filename)
    except DocumentValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{exc.code}: {exc}") from None

    sha256 = hashlib.sha256(content).hexdigest()

    # Dedup decision (brief §9, option B): the same bytes uploaded twice into
    # the SAME workspace return the existing Document instead of creating a
    # duplicate row/reprocessing — deliberately scoped to workspace_id, so
    # this can never merge two different tenants' uploads even if they
    # happen to upload byte-identical files (LEGAL-SECURITY.md §2).
    existing = await session.execute(
        select(Document).where(Document.workspace_id == workspace_id, Document.sha256 == sha256)
    )
    duplicate = existing.scalars().first()
    if duplicate is not None:
        return duplicate

    document_id = uuid.uuid4()
    try:
        storage_path = await get_document_storage().put(workspace_id, document_id, content, suffix=validated.suffix)
    except (DocumentStorageError, DocumentStorageConfigError) as exc:
        # P0 production incident: this was previously unguarded. An uncaught
        # exception here is caught by Starlette's ServerErrorMiddleware,
        # which sits OUTSIDE CORSMiddleware (see Starlette.build_middleware_stack:
        # [ServerErrorMiddleware] + user_middleware([CORSMiddleware, ...]) +
        # [ExceptionMiddleware]) — so the response it produces never gets
        # CORS headers, and the browser reports a misleading "blocked by
        # CORS policy" error for what is actually a storage failure. Raising
        # a real HTTPException here instead routes the response through
        # ExceptionMiddleware -> CORSMiddleware normally, headers intact.
        # DocumentStorageConfigError (e.g. STORAGE_PROVIDER=s3 with no
        # STORAGE_BUCKET set) is raised by get_document_storage() itself,
        # constructing the backend, BEFORE .put() is even reached — still
        # inside this same try, and the real P0 traceback showed this is
        # the exact exception that was escaping uncaught in production.
        # No Document row exists yet at this point either way — nothing to
        # clean up.
        # exc.__cause__ unwraps DocumentStorageError's original (safe, type-name-only)
        # cause for a more informative log; DocumentStorageConfigError has no
        # __cause__ (raised directly), so this falls back to its own type name.
        logger.error("document_storage_put_failed", workspace_id=str(workspace_id), error_type=type(exc.__cause__ or exc).__name__)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Сервис хранения документов временно недоступен — попробуйте позже."
        ) from None

    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        title=file.filename or "untitled",
        original_filename=file.filename,
        media_type=validated.detected_media_type,
        size_bytes=len(content),
        sha256=sha256,
        storage_path=storage_path,
        status=DocumentStatus.UPLOADED,
    )
    document = await DocumentRepository(session, workspace_id).add(document)
    await session.commit()

    engine = DocumentIntelligenceEngine(session)
    await engine.process(document, content, validated.suffix)
    await session.commit()

    return document


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Document:
    document = await DocumentRepository(session, workspace_id).get(document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_document(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = DocumentRepository(session, workspace_id)
    document = await repo.get(document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    storage_path = document.storage_path
    await repo.delete(document_id)  # DocumentChunk rows cascade via ondelete="CASCADE"
    await session.commit()
    if storage_path:
        await get_document_storage().delete(storage_path)


@router.post("/documents/{document_id}/process", response_model=DocumentOut)
async def process_document(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Document:
    """Explicit (re-)run of the extraction/chunking/indexing pipeline —
    idempotent (brief §25), and the documented retry path after a `FAILED`
    upload once the underlying cause is fixed (brief §26).
    """
    document = await DocumentRepository(session, workspace_id).get(document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found in this workspace")
    if document.storage_path is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document has no stored file to process")

    try:
        content = await get_document_storage().get(document.storage_path)
    except (DocumentStorageError, DocumentStorageConfigError) as exc:
        # Sibling gap to the one fixed in upload_document() (same P0 incident
        # class — an unguarded storage call here escapes past CORSMiddleware
        # exactly the same way, see that function's comment for the full
        # Starlette-middleware-ordering explanation). This one was missed
        # because it was never exercised until a real re-process was tried.
        logger.error(
            "document_storage_get_failed", document_id=str(document_id),
            workspace_id=str(workspace_id), error_type=type(exc.__cause__ or exc).__name__,
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Сервис хранения документов временно недоступен — попробуйте позже."
        ) from None
    suffix = "." + document.storage_path.rsplit(".", 1)[-1] if "." in document.storage_path else ""

    engine = DocumentIntelligenceEngine(session)
    await engine.process(document, content, suffix)
    await session.commit()
    return document


@router.get("/documents/{document_id}/text")
async def get_document_text(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    document = await _get_ready_document_or_409(session, workspace_id, document_id)
    return {"document_id": str(document.id), "text": document.extracted_text or ""}


@router.post("/documents/{document_id}/ask", response_model=DocumentAskResponse)
async def ask_document(
    document_id: uuid.UUID,
    body: DocumentAskRequest,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentAskResponse:
    document = await _get_ready_document_or_409(session, workspace_id, document_id)
    result = await ask_documents(session, workspace_id=workspace_id, documents=[document], question=body.question)
    return DocumentAskResponse(
        status=result.status,
        answer=result.answer,
        answer_method=result.answer_method,
        citations=[
            DocumentCitationOut(
                citation_type=c.citation_type,
                document_id=c.document_id,
                document_title=c.document_title,
                page_number=c.page_number,
                section_path=c.section_path,
                excerpt=c.excerpt,
                label=c.label(),
                chunk_id=c.chunk_id,
                content_hash=c.content_hash,
            )
            for c in result.citations
        ],
    )


@router.post("/documents/{document_id}/analyze", response_model=DocumentAnalyzeResponse)
async def analyze_document_endpoint(
    document_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(get_workspace_id),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentAnalyzeResponse:
    document = await _get_ready_document_or_409(session, workspace_id, document_id)
    chunks_result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.workspace_id == workspace_id, DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = list(chunks_result.scalars().all())

    result = await analyze_document(document=document, chunks=chunks)
    return DocumentAnalyzeResponse(
        status=result.status,
        document_type_extracted=result.document_type_extracted,
        extracted_dates=[ExtractedFactOut(**f.__dict__) for f in result.extracted_dates],
        extracted_amounts=[ExtractedFactOut(**f.__dict__) for f in result.extracted_amounts],
        extracted_parties=[ExtractedFactOut(**f.__dict__) for f in result.extracted_parties],
        inferred_obligations=result.inferred_obligations,
        inferred_risks=result.inferred_risks,
        inferred_missing_information=result.inferred_missing_information,
    )
