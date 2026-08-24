from __future__ import annotations

from app.models.matters import CaseRelatedLitigation
from app.repositories.base import WorkspaceScopedRepository


class CaseRelatedLitigationRepository(WorkspaceScopedRepository[CaseRelatedLitigation]):  # type: ignore[type-var]
    model = CaseRelatedLitigation
