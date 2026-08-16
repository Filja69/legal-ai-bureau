from __future__ import annotations

from app.models.matters import CaseDocument
from app.repositories.base import WorkspaceScopedRepository


class CaseDocumentRepository(WorkspaceScopedRepository[CaseDocument]):  # type: ignore[type-var]
    model = CaseDocument
