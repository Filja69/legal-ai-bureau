"""Authentication surface (Phase 7 brief §8). Minimal by design — this is
not a full password-management product (no reset flow, no email
verification): just enough to issue a real, verifiable access token against
a real `User` row. If/when an external IdP is adopted, this endpoint is the
one thing that changes; nothing downstream (JWT verification, membership
checks) needs to know the difference.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_session
from app.models.organization import Role, User, Workspace, WorkspaceMembership
from app.security.deps import CurrentUser, get_current_user
from app.security.jwt import encode_access_token
from app.security.passwords import verify_password
from app.security.rate_limit import rate_limit_by_client_ip

router = APIRouter(tags=["auth"])


class TokenRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


@router.post(
    "/auth/token",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit_by_client_ip("auth_token", get_settings().rate_limit_auth_per_minute))],
)
async def issue_token(body: TokenRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    settings = get_settings()

    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalars().first()

    # Deliberately identical error for "no such user" and "wrong password" —
    # distinguishing them lets a caller enumerate valid emails.
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if user is None:
        raise invalid
    if not verify_password(body.password, user.password_hash):
        raise invalid

    token = encode_access_token(user.id, settings)
    return TokenResponse(access_token=token, expires_in_minutes=settings.jwt_expires_minutes)


class WorkspaceMembershipOut(BaseModel):
    workspace_id: str
    workspace_name: str
    role: str


class CurrentUserOut(BaseModel):
    user_id: str
    email: str | None = None
    name: str | None = None
    is_dev_bypass: bool
    memberships: list[WorkspaceMembershipOut]


@router.get("/auth/me", response_model=CurrentUserOut)
async def whoami(
    user: CurrentUser = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> CurrentUserOut:
    """Phase 8 addition — the frontend needs this to build a workspace
    selector after login: a JWT identifies a user, not which workspace(s)
    they can act in. `X-Workspace-Id` remains what every other route reads;
    this endpoint just tells the client which values are legitimate to send.
    """
    if user.is_dev_bypass:
        return CurrentUserOut(user_id=str(user.user_id), is_dev_bypass=True, memberships=[])

    user_row = await session.get(User, user.user_id)

    result = await session.execute(
        select(WorkspaceMembership, Workspace.name, Role.name)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .join(Role, Role.id == WorkspaceMembership.role_id)
        .where(WorkspaceMembership.user_id == user.user_id)
    )
    memberships = [
        WorkspaceMembershipOut(workspace_id=str(membership.workspace_id), workspace_name=workspace_name, role=role_name.value)
        for membership, workspace_name, role_name in result.all()
    ]

    return CurrentUserOut(
        user_id=str(user.user_id),
        email=user_row.email if user_row else None,
        name=user_row.name if user_row else None,
        is_dev_bypass=False,
        memberships=memberships,
    )
