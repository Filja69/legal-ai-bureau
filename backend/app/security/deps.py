"""AuthN/RBAC FastAPI dependencies (LEGAL-SECURITY.md §4, Phase 7 brief §3-6).

Permission checks live here, applied per-route via `Depends(...)` — never
scattered `if user.role ==` checks inside business logic.

Two dependencies matter:
  - `get_current_user`: WHO is calling — real JWT verification against a
    real `User` row, or (dev/test only, explicit opt-in) a deterministic
    bypass identity. Never silently degrades in production.
  - `get_workspace_id`: WHICH workspace, and is this user actually allowed
    into it — `X-Workspace-Id` is a *request*, not proof of access; a real
    `WorkspaceMembership` row is what grants it (except under dev bypass).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import get_session
from app.models.organization import Role, RoleName, User, Workspace, WorkspaceMembership
from app.security.jwt import TokenError, decode_access_token

logger = structlog.get_logger(__name__)


@dataclass
class CurrentUser:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    # best-effort org-wide role (max across memberships) — used only by
    # require_role() for non-workspace-scoped routes
    role: RoleName | None
    is_dev_bypass: bool = False


_ROLE_RANK = {
    RoleName.VIEWER: 0,
    RoleName.CLIENT: 1,
    RoleName.ANALYST: 2,
    RoleName.PARALEGAL: 3,
    RoleName.LAWYER: 4,
    RoleName.ADMIN: 5,
    RoleName.OWNER: 6,
}


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def _best_role_for_user(session: AsyncSession, user_id: uuid.UUID) -> RoleName | None:
    result = await session.execute(
        select(Role.name).join(WorkspaceMembership, WorkspaceMembership.role_id == Role.id).where(WorkspaceMembership.user_id == user_id)
    )
    roles = result.scalars().all()
    if not roles:
        return None
    return max(roles, key=lambda r: _ROLE_RANK[r])


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    settings = get_settings()
    token = _extract_bearer_token(authorization)

    if authorization is not None and token is None:
        # An Authorization header was *present* but not a well-formed
        # "Bearer <token>" — a failed auth attempt, not an absence of one.
        # Always a hard 401, even under AUTH_DEV_MODE: the bypass exists for
        # callers that send no credentials at all, not to launder malformed
        # ones into success.
        logger.info("auth_failure", reason="malformed_authorization_header")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed Authorization header")

    if token is None:
        # Dev/test bypass — requires BOTH environment=="development" AND an
        # explicit opt-in flag (Phase 7 brief §7). Never applies outside
        # local development, even if AUTH_DEV_MODE is accidentally left true
        # in a shared .env (staging audit §3 — previously only excluded the
        # literal string "production", so ENVIRONMENT=staging would have
        # silently allowed this bypass publicly).
        if settings.environment == "development" and settings.auth_dev_mode:
            return CurrentUser(
                user_id=uuid.uuid4(), organization_id=uuid.uuid4(), role=RoleName.OWNER, is_dev_bypass=True
            )
        logger.info("auth_failure", reason="missing_authorization_header")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Authorization header")

    # A *supplied* token is always validated for real, in every environment
    # and regardless of AUTH_DEV_MODE — dev mode only ever widens the
    # no-token path, it never weakens validation of a token that was given.
    try:
        payload = decode_access_token(token, settings)
    except TokenError:
        logger.info("auth_failure", reason="invalid_or_expired_token")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from None

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError:
        logger.info("auth_failure", reason="invalid_token_subject")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject") from None

    user = await session.get(User, user_id)
    if user is None:
        logger.info("auth_failure", reason="user_not_found")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    role = await _best_role_for_user(session, user_id)
    logger.info("auth_success", user_id=str(user.id))
    return CurrentUser(user_id=user.id, organization_id=user.organization_id, role=role, is_dev_bypass=False)


async def get_workspace_id(
    x_workspace_id: uuid.UUID | None = Header(default=None, alias="X-Workspace-Id"),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> uuid.UUID:
    if x_workspace_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Workspace-Id header is required")

    if user.is_dev_bypass:
        # Dev convenience only — real membership rows don't exist for the
        # random per-request identity the bypass mints, so there is nothing
        # meaningful to check. Never reachable in production (see above).
        return x_workspace_id

    # Phase 7 brief §5: X-Workspace-Id is a request, not proof of access.
    # "Workspace doesn't exist" and "workspace exists but no membership"
    # return the identical 403 — distinguishing them would let a caller
    # enumerate valid workspace ids by probing (brief: "не допускай tenant
    # enumeration").
    workspace = await session.get(Workspace, x_workspace_id)
    if workspace is None:
        logger.info("authorization_denied", user_id=str(user.user_id), reason="workspace_not_found")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this workspace")

    result = await session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == x_workspace_id, WorkspaceMembership.user_id == user.user_id
        )
    )
    if result.scalars().first() is None:
        logger.info(
            "authorization_denied", user_id=str(user.user_id), workspace_id=str(x_workspace_id), reason="no_membership"
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized for this workspace")

    return x_workspace_id


def require_role(minimum: RoleName):
    """Dependency factory — e.g. `Depends(require_role(RoleName.LAWYER))`.

    Used today only by non-workspace-scoped routes (the `/knowledge/*`
    admin surface) — gates on the caller's best role across any of their
    workspace memberships. A user with no memberships at all has no role
    and always fails this check (fails closed, never defaults to allow).
    """

    async def _require_role(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        rank = _ROLE_RANK[user.role] if user.role is not None else -1
        if rank < _ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role >= {minimum.value}")
        return user

    return _require_role
