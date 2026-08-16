"""Tenant isolation — LEGAL-SECURITY.md §2, defense layer 1 (repository scoping).

RLS (defense layer 2) is intentionally permissive at scaffold stage (see
migrations/versions/0001_initial_schema.py and infra/postgres/rls.sql), so
these tests exercise the layer that IS enforced today: every repository
query is scoped to the calling workspace_id and can never return another
workspace's rows, regardless of what's in the database.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.contracts import Contract, ContractType
from app.models.matters import Case
from app.models.organization import Organization, Workspace
from app.repositories.case_repository import CaseRepository
from app.repositories.contract_repository import ContractRepository


async def _make_workspace(db_session, name: str) -> uuid.UUID:
    org = Organization(name=f"Org for {name}")
    db_session.add(org)
    await db_session.flush()
    workspace = Workspace(organization_id=org.id, name=name)
    db_session.add(workspace)
    await db_session.flush()
    return workspace.id


@pytest.mark.asyncio
async def test_repository_never_returns_another_workspaces_case(db_session):
    workspace_a = await _make_workspace(db_session, "Workspace A")
    workspace_b = await _make_workspace(db_session, "Workspace B")

    case_a = Case(workspace_id=workspace_a, title="Case A")
    case_b = Case(workspace_id=workspace_b, title="Case B")
    db_session.add_all([case_a, case_b])
    await db_session.flush()

    repo_a = CaseRepository(db_session, workspace_a)
    results = await repo_a.list()

    assert {c.id for c in results} == {case_a.id}
    assert case_b.id not in {c.id for c in results}


@pytest.mark.asyncio
async def test_repository_get_returns_none_for_foreign_workspace_id(db_session):
    workspace_a = await _make_workspace(db_session, "Workspace A")
    workspace_b = await _make_workspace(db_session, "Workspace B")

    case_b = Case(workspace_id=workspace_b, title="Case B")
    db_session.add(case_b)
    await db_session.flush()

    repo_a = CaseRepository(db_session, workspace_a)
    assert await repo_a.get(case_b.id) is None


@pytest.mark.asyncio
async def test_repository_add_rejects_mismatched_workspace_id(db_session):
    workspace_a = await _make_workspace(db_session, "Workspace A")
    workspace_b = await _make_workspace(db_session, "Workspace B")

    repo_a = CaseRepository(db_session, workspace_a)
    mismatched_case = Case(workspace_id=workspace_b, title="Should be rejected")

    with pytest.raises(ValueError):
        await repo_a.add(mismatched_case)


# --- Contract Intelligence (Phase 4) — same WorkspaceScopedRepository base as
# Case, but never had a dedicated regression test until Phase 6.5's audit
# explicitly asked for one (brief §9: Contract is named alongside Case). ---


@pytest.mark.asyncio
async def test_contract_repository_never_returns_another_workspaces_contract(db_session):
    workspace_a = await _make_workspace(db_session, "Workspace A")
    workspace_b = await _make_workspace(db_session, "Workspace B")

    contract_a = Contract(workspace_id=workspace_a, title="Contract A", contract_type=ContractType.SERVICE)
    contract_b = Contract(workspace_id=workspace_b, title="Contract B", contract_type=ContractType.SERVICE)
    db_session.add_all([contract_a, contract_b])
    await db_session.flush()

    repo_a = ContractRepository(db_session, workspace_a)
    results = await repo_a.list()

    assert {c.id for c in results} == {contract_a.id}
    assert contract_b.id not in {c.id for c in results}


@pytest.mark.asyncio
async def test_contract_repository_get_returns_none_for_foreign_workspace_id(db_session):
    workspace_a = await _make_workspace(db_session, "Workspace A")
    workspace_b = await _make_workspace(db_session, "Workspace B")

    contract_b = Contract(workspace_id=workspace_b, title="Contract B", contract_type=ContractType.SERVICE)
    db_session.add(contract_b)
    await db_session.flush()

    repo_a = ContractRepository(db_session, workspace_a)
    assert await repo_a.get(contract_b.id) is None


@pytest.mark.asyncio
async def test_contract_repository_add_rejects_mismatched_workspace_id(db_session):
    workspace_a = await _make_workspace(db_session, "Workspace A")
    workspace_b = await _make_workspace(db_session, "Workspace B")

    repo_a = ContractRepository(db_session, workspace_a)
    mismatched_contract = Contract(workspace_id=workspace_b, title="Should be rejected", contract_type=ContractType.SERVICE)

    with pytest.raises(ValueError):
        await repo_a.add(mismatched_contract)


@pytest.mark.asyncio
async def test_public_legal_kb_has_no_workspace_column(db_session):
    """LawVersion/LegalSource/EmbeddingChunk (the shared public Knowledge
    Base) must structurally have no `workspace_id` — this is what makes
    "tenant document silently enters the public KB" impossible by
    construction rather than by convention (LEGAL-SECURITY.md §2,
    Phase 6.5 brief §9: "Tenant document -> PUBLIC LEGAL KB никогда не
    происходит автоматически").
    """
    from app.models.embedding_chunk import EmbeddingChunk
    from app.models.legal_knowledge import LawVersion, LegalSource

    for model in (LawVersion, LegalSource, EmbeddingChunk):
        assert not hasattr(model, "workspace_id"), f"{model.__name__} must never carry workspace_id — it is shared public data"
