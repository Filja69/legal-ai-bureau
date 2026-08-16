from __future__ import annotations

from app.models.matters import Document
from app.repositories.base import WorkspaceScopedRepository


class DocumentRepository(WorkspaceScopedRepository[Document]):  # type: ignore[type-var]
    # See app/repositories/case_repository.py for why this ignore is safe.
    model = Document
