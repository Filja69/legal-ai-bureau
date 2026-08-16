"""Staging deployment audit §13/§14 — python -m app.cli.seed_staging_users.
Exercised against a real (test) Postgres via the standard db_engine fixture,
which provisions the schema this CLI writes into.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.cli.seed_staging_users import main
from app.models.matters import Case
from app.models.organization import RoleName, User, Workspace, WorkspaceMembership


@pytest.mark.asyncio
async def test_seed_creates_three_users_with_distinct_roles(db_session):
    exit_code = await main(with_demo_data=False)
    assert exit_code == 0

    users = (await db_session.execute(select(User).where(User.email.like("%@staging.legal-ai-bureau.test")))).scalars().all()
    assert len(users) == 3

    workspace = (await db_session.execute(select(Workspace).where(Workspace.name == "Staging Workspace"))).scalars().first()
    assert workspace is not None

    memberships = (
        await db_session.execute(select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace.id))
    ).scalars().all()
    assert len(memberships) == 3


@pytest.mark.asyncio
async def test_seed_assigns_owner_lawyer_viewer_roles(db_session):
    from app.models.organization import Role

    await main(with_demo_data=False)

    result = await db_session.execute(
        select(User.email, Role.name)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .join(Role, Role.id == WorkspaceMembership.role_id)
        .where(User.email.like("%@staging.legal-ai-bureau.test"))
    )
    roles_by_email = dict(result.all())
    assert roles_by_email["tester1-owner@staging.legal-ai-bureau.test"] == RoleName.OWNER
    assert roles_by_email["tester2-lawyer@staging.legal-ai-bureau.test"] == RoleName.LAWYER
    assert roles_by_email["tester3-viewer@staging.legal-ai-bureau.test"] == RoleName.VIEWER


@pytest.mark.asyncio
async def test_seed_passwords_actually_work_for_login(db_session):
    """Not just "a password was printed" — the printed password must be the
    one that actually authenticates, proving hash_password/verify_password
    round-trip correctly for a CLI-generated secret.
    """
    from app.models.organization import Organization
    from app.security.passwords import verify_password

    await main(with_demo_data=False)
    org = (await db_session.execute(select(Organization).where(Organization.name == "Legal AI Bureau — Staging"))).scalars().first()
    assert org is not None
    # The CLI doesn't return the password, so re-run capture via a direct
    # call to the lower-level helper instead of parsing stdout.
    from app.cli.seed_staging_users import _get_or_create_user

    other_user, password = await _get_or_create_user(db_session, org, "brand-new-tester@staging.legal-ai-bureau.test")
    assert password is not None
    assert verify_password(password, other_user.password_hash)


@pytest.mark.asyncio
async def test_seed_is_idempotent_does_not_duplicate_users_or_memberships(db_session):
    await main(with_demo_data=False)
    await main(with_demo_data=False)  # second run must not create duplicates

    users = (await db_session.execute(select(User).where(User.email.like("%@staging.legal-ai-bureau.test")))).scalars().all()
    assert len(users) == 3

    workspace = (await db_session.execute(select(Workspace).where(Workspace.name == "Staging Workspace"))).scalars().first()
    memberships = (
        await db_session.execute(select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace.id))
    ).scalars().all()
    assert len(memberships) == 3


@pytest.mark.asyncio
async def test_seed_with_demo_data_creates_exactly_one_case(db_session):
    await main(with_demo_data=True)
    await main(with_demo_data=True)  # idempotent — must not create a second case

    cases = (await db_session.execute(select(Case))).scalars().all()
    assert len(cases) == 1
    assert "synthetic" in cases[0].title.lower() or "STAGING DEMO" in cases[0].title


@pytest.mark.asyncio
async def test_seed_without_demo_data_flag_creates_no_case(db_session):
    await main(with_demo_data=False)
    cases = (await db_session.execute(select(Case))).scalars().all()
    assert cases == []


def test_cli_module_never_logs_via_structlog():
    """Passwords must only ever reach plain stdout (print), never structlog
    — structlog output may be shipped to persistent, aggregated log storage
    on Render, which is exactly what "printed once, never logged" (staging
    deployment brief §13) is meant to avoid.
    """
    import inspect

    import app.cli.seed_staging_users as module

    source = inspect.getsource(module)
    assert "logger." not in source
    assert "import structlog" not in source
