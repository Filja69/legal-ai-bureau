from __future__ import annotations

from app.models.matters import CasePartyRelationship
from app.repositories.base import WorkspaceScopedRepository


class CasePartyRelationshipRepository(WorkspaceScopedRepository[CasePartyRelationship]):  # type: ignore[type-var]
    model = CasePartyRelationship
