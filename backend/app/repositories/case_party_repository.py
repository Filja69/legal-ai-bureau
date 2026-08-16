from __future__ import annotations

from app.models.matters import CaseParty
from app.repositories.base import WorkspaceScopedRepository


class CasePartyRepository(WorkspaceScopedRepository[CaseParty]):  # type: ignore[type-var]
    model = CaseParty
