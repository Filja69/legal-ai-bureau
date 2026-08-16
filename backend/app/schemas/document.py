from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.matters import DocumentStatus, DocumentType


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    document_type: DocumentType
    original_filename: str | None
    media_type: str | None
    size_bytes: int | None
    sha256: str | None
    status: DocumentStatus
    processing_error: str | None
    created_at: datetime | None = None
    processed_at: datetime | None = None
    doc_metadata: dict = {}


class DocumentAskRequest(BaseModel):
    question: str


class DocumentCitationOut(BaseModel):
    citation_type: str
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    section_path: str | None
    excerpt: str
    label: str
    chunk_id: uuid.UUID | None = None
    content_hash: str | None = None


class DocumentAskResponse(BaseModel):
    status: str
    answer: str
    citations: list[DocumentCitationOut]
    answer_method: str = "llm"


class ExtractedFactOut(BaseModel):
    value: str
    provenance: str
    kind: str


class DocumentAnalyzeResponse(BaseModel):
    status: str
    document_type_extracted: str | None
    extracted_dates: list[ExtractedFactOut]
    extracted_amounts: list[ExtractedFactOut]
    extracted_parties: list[ExtractedFactOut]
    inferred_obligations: list[str]
    inferred_risks: list[str]
    inferred_missing_information: list[str]
