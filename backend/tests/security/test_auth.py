"""Phase 7 auth test matrix (brief §9) — JWT validation, workspace
membership authorization, RBAC, and regression across the real API surface.
Every test here uses REAL User/WorkspaceMembership rows and REAL JWTs — the
dev bypass (AUTH_DEV_MODE, used by the rest of the test suite) is never
exercised in this file.
"""
from __future__ import annotations

import uuid

import pytest
from jose import jwt as jose_jwt

from app.config.settings import Settings, get_settings
from app.models.organization import RoleName
from app.security import deps as deps_module
from app.security.jwt import decode_access_token, encode_access_token
from tests.security.auth_factories import (
    TEST_PASSWORD,
    bearer,
    make_membership,
    make_org_and_workspace,
    make_user,
    random_workspace_id,
    token_for,
)


def _prod_no_dev_mode(monkeypatch) -> None:
    """Simulates production: environment=production, AUTH_DEV_MODE has no
    effect there regardless of its value (brief §7)."""
    settings = Settings(environment="production", auth_dev_mode=True, jwt_secret=get_settings().jwt_secret)
    monkeypatch.setattr(deps_module, "get_settings", lambda: settings)


# --- JWT-level tests (brief §9 "JWT: 8+ tests") ---


def test_jwt_roundtrip_valid_token():
    settings = get_settings()
    user_id = uuid.uuid4()
    token = encode_access_token(user_id, settings)
    payload = decode_access_token(token, settings)
    assert payload["sub"] == str(user_id)
    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.jwt_audience


def test_jwt_rejects_malformed_token():
    from app.security.jwt import TokenError

    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt", get_settings())


def test_jwt_rejects_wrong_signature():
    from app.security.jwt import TokenError

    settings = get_settings()
    token = encode_access_token(uuid.uuid4(), settings)
    wrong_secret_settings = Settings(jwt_secret="a-completely-different-secret")
    with pytest.raises(TokenError):
        decode_access_token(token, wrong_secret_settings)


def test_jwt_rejects_expired_token():
    from app.security.jwt import TokenError

    settings = get_settings()
    token = encode_access_token(uuid.uuid4(), settings, expires_minutes=-1)  # already expired
    with pytest.raises(TokenError):
        decode_access_token(token, settings)


def test_jwt_rejects_wrong_issuer():
    from app.security.jwt import TokenError

    settings = get_settings()
    bad_claims = {
        "sub": str(uuid.uuid4()), "iss": "someone-else", "aud": settings.jwt_audience,
    }
    token = jose_jwt.encode(bad_claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError):
        decode_access_token(token, settings)


def test_jwt_rejects_wrong_audience():
    from app.security.jwt import TokenError

    settings = get_settings()
    bad_claims = {
        "sub": str(uuid.uuid4()), "iss": settings.jwt_issuer, "aud": "someone-elses-api",
    }
    token = jose_jwt.encode(bad_claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(TokenError):
        decode_access_token(token, settings)


def test_jwt_expires_minutes_is_configurable():
    settings = get_settings()
    token = encode_access_token(uuid.uuid4(), settings, expires_minutes=1)
    payload = decode_access_token(token, settings)
    assert payload["exp"] - payload["iat"] == 60


def test_jwt_default_expiry_matches_settings():
    settings = get_settings()
    token = encode_access_token(uuid.uuid4(), settings)
    payload = decode_access_token(token, settings)
    assert payload["exp"] - payload["iat"] == settings.jwt_expires_minutes * 60


# --- get_current_user / production fail-closed (brief §7, §9 negative) ---


@pytest.mark.asyncio
async def test_production_without_token_is_401(client, db_session, monkeypatch):
    _prod_no_dev_mode(monkeypatch)
    response = await client.get("/api/v1/legal/cases", headers={"X-Workspace-Id": str(random_workspace_id())})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_staging_without_token_is_401(client, db_session, monkeypatch):
    """Staging audit §3 — previously the dev bypass only excluded the
    literal string "production", so ENVIRONMENT=staging with AUTH_DEV_MODE
    left over from a copied .env would have publicly bypassed auth.
    """
    settings = Settings(environment="staging", auth_dev_mode=True, jwt_secret=get_settings().jwt_secret)
    monkeypatch.setattr(deps_module, "get_settings", lambda: settings)
    response = await client.get("/api/v1/legal/cases", headers={"X-Workspace-Id": str(random_workspace_id())})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_no_token_in_dev_mode_uses_bypass_identity(client, db_session):
    # This is the existing behavior the rest of the suite relies on —
    # locked in explicitly here as a regression guard.
    response = await client.get("/api/v1/legal/cases", headers={"X-Workspace-Id": str(random_workspace_id())})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_malformed_authorization_header_is_401(client, db_session):
    response = await client.get(
        "/api/v1/legal/cases",
        headers={"Authorization": "not-a-bearer-token", "X-Workspace-Id": str(random_workspace_id())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_is_401(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "expired@example.com")
    await make_membership(db_session, user, workspace, RoleName.OWNER)
    await db_session.commit()

    token = token_for(user, get_settings(), expires_minutes=-1)
    response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(workspace.id)}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_wrong_signature_is_401(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "wrongsig@example.com")
    await make_membership(db_session, user, workspace, RoleName.OWNER)
    await db_session.commit()

    other_settings = Settings(jwt_secret="attacker-controlled-secret")
    forged = encode_access_token(user.id, other_settings)
    response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(forged), "X-Workspace-Id": str(workspace.id)}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_for_nonexistent_user_is_401(client, db_session):
    token = encode_access_token(uuid.uuid4(), get_settings())  # well-signed, but no such User row
    response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(random_workspace_id())}
    )
    assert response.status_code == 401


# --- Membership / workspace authorization (brief §9) ---


@pytest.mark.asyncio
async def test_valid_token_and_membership_grants_access(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "member@example.com")
    await make_membership(db_session, user, workspace, RoleName.LAWYER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(workspace.id)}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_valid_token_no_membership_is_403(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "nomember@example.com")
    # deliberately no make_membership() call
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(workspace.id)}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_nonexistent_workspace_is_403_not_404(client, db_session):
    """Same status as 'no membership' — brief §5: don't let a caller
    distinguish 'workspace doesn't exist' from 'exists but I can't see it'."""
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "probe@example.com")
    await make_membership(db_session, user, workspace, RoleName.OWNER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(uuid.uuid4())}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_a_cannot_access_workspace_b(client, db_session):
    """The central cross-tenant regression (brief §9/§21)."""
    org_a, workspace_a = await make_org_and_workspace(db_session, "Org A")
    org_b, workspace_b = await make_org_and_workspace(db_session, "Org B")
    user_a = await make_user(db_session, org_a, "usera@example.com")
    await make_membership(db_session, user_a, workspace_a, RoleName.OWNER)
    await db_session.commit()

    token_a = token_for(user_a, get_settings())

    own_workspace = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token_a), "X-Workspace-Id": str(workspace_a.id)}
    )
    assert own_workspace.status_code == 200

    other_workspace = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token_a), "X-Workspace-Id": str(workspace_b.id)}
    )
    assert other_workspace.status_code == 403


@pytest.mark.asyncio
async def test_missing_workspace_header_is_400(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "noheader@example.com")
    await make_membership(db_session, user, workspace, RoleName.OWNER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get("/api/v1/legal/cases", headers=bearer(token))
    assert response.status_code == 400


# --- RBAC (brief §6/§9) — require_role() on /knowledge/* admin routes ---


@pytest.mark.asyncio
async def test_owner_role_can_access_admin_knowledge_route(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "owner@example.com")
    await make_membership(db_session, user, workspace, RoleName.OWNER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get("/api/v1/legal/knowledge/index-status", headers=bearer(token))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_role_can_access_admin_knowledge_route(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "admin@example.com")
    await make_membership(db_session, user, workspace, RoleName.ADMIN)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get("/api/v1/legal/knowledge/index-status", headers=bearer(token))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_viewer_role_forbidden_from_admin_knowledge_route(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "viewer@example.com")
    await make_membership(db_session, user, workspace, RoleName.VIEWER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get("/api/v1/legal/knowledge/index-status", headers=bearer(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_with_zero_memberships_forbidden_from_admin_knowledge_route(client, db_session):
    org, _workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "nomembershipatall@example.com")
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get("/api/v1/legal/knowledge/index-status", headers=bearer(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_membership_removal_revokes_access(client, db_session):
    """'Revoked/inactive membership => 403' (brief §9) — modeled here as
    deleting the membership row, since the schema has no separate
    active/inactive flag; the effect (access removed) is what's tested."""
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "revoked@example.com")
    membership = await make_membership(db_session, user, workspace, RoleName.LAWYER)
    await db_session.commit()

    token = token_for(user, get_settings())
    before = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(workspace.id)}
    )
    assert before.status_code == 200

    await db_session.delete(membership)
    await db_session.commit()

    after = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(workspace.id)}
    )
    assert after.status_code == 403


# --- /auth/token endpoint ---


@pytest.mark.asyncio
async def test_auth_token_endpoint_issues_working_token(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "login@example.com")
    await make_membership(db_session, user, workspace, RoleName.LAWYER)
    await db_session.commit()

    token_response = await client.post(
        "/api/v1/legal/auth/token", json={"email": "login@example.com", "password": TEST_PASSWORD}
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]

    api_response = await client.get(
        "/api/v1/legal/cases", headers={**bearer(token), "X-Workspace-Id": str(workspace.id)}
    )
    assert api_response.status_code == 200


@pytest.mark.asyncio
async def test_auth_token_endpoint_rejects_wrong_password(client, db_session):
    org, _workspace = await make_org_and_workspace(db_session)
    await make_user(db_session, org, "wrongpass@example.com")
    await db_session.commit()

    response = await client.post(
        "/api/v1/legal/auth/token", json={"email": "wrongpass@example.com", "password": "not the right password"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_token_endpoint_rejects_unknown_email(client, db_session):
    response = await client.post(
        "/api/v1/legal/auth/token", json={"email": "nobody@example.com", "password": "anything"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_me_returns_workspace_memberships(client, db_session):
    org, workspace = await make_org_and_workspace(db_session, "Me Org")
    user = await make_user(db_session, org, "me@example.com")
    await make_membership(db_session, user, workspace, RoleName.LAWYER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.get("/api/v1/legal/auth/me", headers=bearer(token))
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == "me@example.com"
    assert body["is_dev_bypass"] is False
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["workspace_id"] == str(workspace.id)
    assert body["memberships"][0]["role"] == "lawyer"


@pytest.mark.asyncio
async def test_auth_me_requires_authentication(client, db_session, monkeypatch):
    _prod_no_dev_mode(monkeypatch)
    response = await client.get("/api/v1/legal/auth/me")
    assert response.status_code == 401


# --- Regression across the real API surface (brief §9 "Regression") ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/legal/cases"),
        ("GET", "/api/v1/legal/contracts"),
    ],
)
async def test_workspace_scoped_routes_enforce_membership(client, db_session, method, path):
    org_a, workspace_a = await make_org_and_workspace(db_session, "Org RegA")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Org RegB")
    user_a = await make_user(db_session, org_a, f"reg-{path.replace('/', '-')}@example.com")
    await make_membership(db_session, user_a, workspace_a, RoleName.LAWYER)
    await db_session.commit()

    token = token_for(user_a, get_settings())
    request = client.build_request(method, path, headers={**bearer(token), "X-Workspace-Id": str(workspace_b.id)})
    response = await client.send(request)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_research_endpoint_enforces_membership(client, db_session):
    org_a, workspace_a = await make_org_and_workspace(db_session, "Org ResA")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Org ResB")
    user_a = await make_user(db_session, org_a, "research-reg@example.com")
    await make_membership(db_session, user_a, workspace_a, RoleName.LAWYER)
    await db_session.commit()

    token = token_for(user_a, get_settings())
    response = await client.post(
        "/api/v1/legal/research",
        json={"question": "test"},
        headers={**bearer(token), "X-Workspace-Id": str(workspace_b.id)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_knowledge_reindex_requires_admin_role(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "reindex-viewer@example.com")
    await make_membership(db_session, user, workspace, RoleName.VIEWER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.post("/api/v1/legal/knowledge/reindex", json={"dry_run": True}, headers=bearer(token))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_debug_requires_admin_role_with_real_auth(client, db_session):
    org, workspace = await make_org_and_workspace(db_session)
    user = await make_user(db_session, org, "debug-viewer@example.com")
    await make_membership(db_session, user, workspace, RoleName.VIEWER)
    await db_session.commit()

    token = token_for(user, get_settings())
    response = await client.post(
        "/api/v1/legal/search/debug", json={"query": "test", "top_k": 5}, headers=bearer(token)
    )
    assert response.status_code == 403
