"""Staging test-account seeding — staging deployment audit §13/§14.

    python -m app.cli.seed_staging_users [--with-demo-data]

Creates one Organization + Workspace and three staging test users with
distinct roles, so external testers can be handed working credentials
without ever hardcoding them into the application. `RoleName` (see
app/models/organization.py) has no literal "MEMBER" value — Tester 2 uses
RoleName.LAWYER, the closest equivalent to a regular working member in this
app's actual role vocabulary, rather than inventing a new role.

Passwords are generated at runtime (`secrets.token_urlsafe`, never a
hardcoded or predictable value) and printed to stdout exactly once — never
passed through `structlog` (which may ship to persistent log aggregation on
Render), never written to any file this script controls. Whoever runs this
is responsible for capturing the printed output somewhere safe immediately;
it cannot be recovered afterward (only re-run to mint new passwords for
users that don't yet exist).

Safe to re-run: existing users (matched by email) and their memberships are
left alone, never duplicated or silently reset. Re-running after all three
testers already exist just confirms that and issues no new passwords.

`--with-demo-data` seeds exactly one synthetic Case (title/party names
explicitly marked "(synthetic)") — never a fake legal source, never
anything that could be mistaken for real evidence (LEGAL-PRD.md's "AI does
not invent" principle applies to demo data too). Deliberately does not seed
demo documents/contracts/research — those require the real upload/analysis
pipeline and are better exercised live via the smoke test in
docs/STAGING-DEPLOYMENT.md than faked here.
"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session_factory
from app.models.matters import Case, CaseStatus
from app.models.organization import Organization, RoleName, User, Workspace, WorkspaceMembership
from app.security.passwords import hash_password
from app.security.seed import get_or_create_role

_ORG_NAME = "Legal AI Bureau — Staging"
_WORKSPACE_NAME = "Staging Workspace"

_TESTERS: list[tuple[str, RoleName, str]] = [
    ("tester1-owner@staging.legal-ai-bureau.test", RoleName.OWNER, "Tester 1 (Owner)"),
    ("tester2-lawyer@staging.legal-ai-bureau.test", RoleName.LAWYER, "Tester 2 (Member)"),
    ("tester3-viewer@staging.legal-ai-bureau.test", RoleName.VIEWER, "Tester 3 (Viewer)"),
]


def _print(*lines: str) -> None:
    for line in lines:
        print(line)  # noqa: T201 — this is a CLI, stdout is the product


async def _get_or_create_org_and_workspace(session: AsyncSession) -> tuple[Organization, Workspace]:
    org_result = await session.execute(select(Organization).where(Organization.name == _ORG_NAME))
    org = org_result.scalars().first()
    if org is None:
        org = Organization(name=_ORG_NAME)
        session.add(org)
        await session.flush()

    workspace_result = await session.execute(
        select(Workspace).where(Workspace.organization_id == org.id, Workspace.name == _WORKSPACE_NAME)
    )
    workspace = workspace_result.scalars().first()
    if workspace is None:
        workspace = Workspace(organization_id=org.id, name=_WORKSPACE_NAME)
        session.add(workspace)
        await session.flush()
    return org, workspace


async def _get_or_create_user(session: AsyncSession, org: Organization, email: str) -> tuple[User, str | None]:
    """Returns (user, password) — password is None when the user already
    existed (no new secret is ever minted for an existing account here).
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user is not None:
        return user, None

    password = secrets.token_urlsafe(12)
    user = User(organization_id=org.id, email=email, name=email.split("@")[0], password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user, password


async def _ensure_membership(session: AsyncSession, user: User, workspace: Workspace, role_name: RoleName) -> None:
    result = await session.execute(
        select(WorkspaceMembership).where(
            WorkspaceMembership.user_id == user.id, WorkspaceMembership.workspace_id == workspace.id
        )
    )
    if result.scalars().first() is not None:
        return
    role = await get_or_create_role(session, role_name)
    session.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role_id=role.id))
    await session.flush()


async def _seed_demo_case(session: AsyncSession, workspace: Workspace) -> bool:
    existing = await session.execute(select(Case).where(Case.workspace_id == workspace.id))
    if existing.scalars().first() is not None:
        return False
    session.add(
        Case(
            id=uuid.uuid4(),
            workspace_id=workspace.id,
            title="STAGING DEMO — Ромашка v. Поставщик (synthetic, not a real dispute)",
            status=CaseStatus.OPEN,
            client_name='ООО "Ромашка" (synthetic)',
            counterparty_name='ООО "Поставщик" (synthetic)',
            matter_type="contract dispute (demo)",
        )
    )
    await session.flush()
    return True


async def main(*, with_demo_data: bool) -> int:
    session_factory = get_session_factory()
    async with session_factory() as session:
        org, workspace = await _get_or_create_org_and_workspace(session)

        _print(
            "=" * 70,
            "STAGING TEST CREDENTIALS — copy these now. They are shown only once",
            "and cannot be recovered later (only reset by deleting the user row).",
            f"Workspace: {workspace.name} ({workspace.id})",
            "=" * 70,
        )

        any_created = False
        for email, role_name, label in _TESTERS:
            user, password = await _get_or_create_user(session, org, email)
            await _ensure_membership(session, user, workspace, role_name)
            if password is not None:
                any_created = True
                _print(label, f"  email:    {email}", f"  password: {password}", f"  role:     {role_name.value}")
            else:
                _print(f"{label} already exists ({email}) — left unchanged, no new password issued.")
        _print("=" * 70)

        if with_demo_data:
            seeded = await _seed_demo_case(session, workspace)
            _print(
                "Seeded one synthetic demo case."
                if seeded
                else "Demo case already exists — left unchanged."
            )

        await session.commit()

        if not any_created:
            _print("No new users were created — all three testers already existed.")

        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-demo-data", action="store_true", help="Also seed one synthetic demo case")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(with_demo_data=args.with_demo_data)))
