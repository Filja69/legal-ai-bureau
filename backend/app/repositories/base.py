"""Base workspace-scoped repository (LEGAL-SECURITY.md §2, defense layer 1).

Every tenant-table repository extends this and MUST route reads/writes
through `_scoped()` — a query built without it is a tenant-isolation bug,
not a style nit. RLS (see migrations/versions/0001_initial_schema.py) is
the second, independent layer of defense, not a substitute for this one.
"""
from __future__ import annotations

import uuid
from typing import Generic, Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class _WorkspaceScopedModel(Protocol):
    """Structural bound for ModelT — every tenant ORM model has these columns
    (see app/models/mixins.py UUIDPrimaryKeyMixin + workspace_fk()).
    """

    id: uuid.UUID
    workspace_id: uuid.UUID


ModelT = TypeVar("ModelT", bound=_WorkspaceScopedModel)


class WorkspaceScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession, workspace_id: uuid.UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id

    def _scoped(self):
        return select(self.model).where(self.model.workspace_id == self._workspace_id)

    async def list(self) -> list[ModelT]:
        result = await self._session.execute(self._scoped())
        return list(result.scalars().all())

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        result = await self._session.execute(self._scoped().where(self.model.id == entity_id))
        return result.scalars().first()

    async def add(self, entity: ModelT) -> ModelT:
        if getattr(entity, "workspace_id", None) != self._workspace_id:
            raise ValueError("Entity workspace_id does not match repository's scoped workspace_id")
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID) -> bool:
        """Returns False for "not found in this workspace" — same shape as
        `get()` returning None — never distinguishes "doesn't exist" from
        "exists in another workspace" (LEGAL-SECURITY.md §2).
        """
        entity = await self.get(entity_id)
        if entity is None:
            return False
        await self._session.delete(entity)
        await self._session.flush()
        return True
