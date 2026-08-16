"""Shared factories for the Phase 7 auth test matrix — creates real
User/Workspace/WorkspaceMembership rows and real JWTs, never dev-bypass
shortcuts, so these tests exercise the actual enforcement path.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import Settings
from app.models.organization import Organization, RoleName, User, Workspace, WorkspaceMembership
from app.security.jwt import encode_access_token
from app.security.passwords import hash_password
from app.security.seed import get_or_create_role

TEST_PASSWORD = "correct horse battery staple"


async def make_org_and_workspace(session: AsyncSession, name: str = "Test Org") -> tuple[Organization, Workspace]:
    org = Organization(name=name)
    session.add(org)
    await session.flush()
    workspace = Workspace(organization_id=org.id, name=f"{name} Workspace")
    session.add(workspace)
    await session.flush()
    return org, workspace


async def make_user(session: AsyncSession, org: Organization, email: str, password: str = TEST_PASSWORD) -> User:
    user = User(organization_id=org.id, email=email, name=email.split("@")[0], password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def make_membership(session: AsyncSession, user: User, workspace: Workspace, role_name: RoleName) -> WorkspaceMembership:
    role = await get_or_create_role(session, role_name)
    membership = WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role_id=role.id)
    session.add(membership)
    await session.flush()
    return membership


def token_for(user: User, settings: Settings, **kwargs) -> str:
    return encode_access_token(user.id, settings, **kwargs)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def random_workspace_id() -> uuid.UUID:
    return uuid.uuid4()
