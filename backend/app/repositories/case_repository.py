from __future__ import annotations

from app.models.matters import Case
from app.repositories.base import WorkspaceScopedRepository


class CaseRepository(WorkspaceScopedRepository[Case]):  # type: ignore[type-var]
    # mypy + the SQLAlchemy plugin don't structurally match InstrumentedAttribute
    # descriptors against the Protocol bound on ModelT, even though instance
    # access (Case().id, Case().workspace_id) is correctly typed as uuid.UUID —
    # a known friction point, not a real type error. See app/repositories/base.py.
    model = Case
