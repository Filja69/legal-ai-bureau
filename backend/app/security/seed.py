"""Role lookup-table seeding — `Role` is a table (not a bare enum column) so
future custom roles don't need a migration (see app/models/organization.py),
but that means every `RoleName` needs a corresponding row before any
`WorkspaceMembership` can reference it. Idempotent — safe to call repeatedly.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Role, RoleName


async def get_or_create_role(session: AsyncSession, role_name: RoleName) -> Role:
    result = await session.execute(select(Role).where(Role.name == role_name))
    role = result.scalars().first()
    if role is not None:
        return role
    role = Role(name=role_name)
    session.add(role)
    await session.flush()
    return role
