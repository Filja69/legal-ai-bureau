from __future__ import annotations

from app.models.matters import CaseHypothesis
from app.repositories.base import WorkspaceScopedRepository


class CaseHypothesisRepository(WorkspaceScopedRepository[CaseHypothesis]):  # type: ignore[type-var]
    model = CaseHypothesis
