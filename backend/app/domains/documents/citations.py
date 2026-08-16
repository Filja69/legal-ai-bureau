"""Document citation shape — Phase 9.2 brief §18. A citation into a tenant's
own uploaded document is NEVER formatted like a law citation ("ГК РФ, ст.
309") — it has its own provenance type pointing at a page/clause inside a
specific document, because a client's contract is evidence, not legal
authority (brief §17).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class DocumentCitation:
    citation_type: str  # "document_evidence" (LLM-reasoned) or "document_evidence_extracted"
    # (deterministic regex match, no LLM involved) — never "legal_authority"
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    section_path: str | None
    excerpt: str
    chunk_id: uuid.UUID | None = None
    content_hash: str | None = None

    def label(self) -> str:
        location = self.section_path or (f"стр. {self.page_number}" if self.page_number else None)
        if location:
            return f"{self.document_title}, {location}"
        return self.document_title
