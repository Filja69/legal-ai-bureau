"""Legal Theory Layer (P1) — the legal-authority verification half, run
through the real API endpoint against the real LegalResearchEngine (using
the test environment's MockLLMProvider — see tests/conftest.py's
LLM_PROVIDER=mock default — never a live provider). The deterministic
fact-pattern half is unit-tested exhaustively in tests/unit/test_legal_theory.py;
this file proves the fail-closed wiring end-to-end: with no legal source
ingested into the Knowledge Base (the actual state of a fresh test DB,
and — as observed directly — of production today), no theory is ever
promoted past COUNSEL_HYPOTHESIS.
"""
from __future__ import annotations

import io

import pytest

from tests.security.auth_factories import make_org_and_workspace


async def _create_case(client, workspace_id, title="Synthetic Legal Theory Case"):
    response = await client.post("/api/v1/legal/cases", json={"title": title}, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    return response.json()["id"]


async def _upload_ready_document(client, workspace_id, filename: str, text: str):
    files = {"file": (filename, io.BytesIO(text.encode("utf-8")), "text/plain")}
    response = await client.post("/api/v1/legal/documents", files=files, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    return response.json()["id"]


async def _attach(client, workspace_id, case_id, document_id, role):
    resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id, "role": role},
        headers={"X-Workspace-Id": str(workspace_id)},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_empty_case_never_calls_the_research_engine(client, db_session):
    """No payments at all — preconditions_met is False, so this must return
    a counsel_hypothesis immediately without touching LegalResearchEngine
    (proven by research_id staying None)."""
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    response = await client.post(f"/api/v1/legal/cases/{case_id}/legal-theories", headers=headers)
    assert response.status_code == 200
    theories = response.json()
    assert len(theories) == 1
    theory = theories[0]
    assert theory["classification"] == "counsel_hypothesis"
    assert theory["verified_legal_authority"] == []
    assert theory["research_id"] is None


@pytest.mark.asyncio
async def test_real_fact_pattern_with_empty_knowledge_base_fails_closed(client, db_session):
    """A genuine, non-trivial fact pattern (repeated payments referencing a
    contract, an unsigned draft) — the deterministic half must populate
    supporting/contradicting facts and evidence gaps, but with no legal
    source ingested anywhere in this test database, the research engine
    can never return a VERIFIED citation, so classification must stay
    COUNSEL_HYPOTHESIS and verified_legal_authority must stay empty.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)

    payment_text = (
        'ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 1 05.03.2025\n'
        'Сумма 700000-00\n'
        'ООО "СИНТЕТИК ПЛЕЙНТИФФ"\n'
        'Плательщик\n'
        'ООО "СИНТЕТИК ДИФЕНДАНТ"\n'
        'Получатель\n'
        'Назначение платежа Перечисление средств по договору процентного займа от 01.03.2025г.\n'
        'Исполнено 05.03.2025\n'
    )
    payment_id = await _upload_ready_document(client, workspace.id, "payment.txt", payment_text)
    await _attach(client, workspace.id, case_id, payment_id, "payment_document")

    contract_text = "Проект договора процентного займа от 01.03.2025 (не подписан). Займодавец передает Заемщику 700000 рублей."
    contract_id = await _upload_ready_document(client, workspace.id, "contract.txt", contract_text)
    await _attach(client, workspace.id, case_id, contract_id, "contract")

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200

    response = await client.post(f"/api/v1/legal/cases/{case_id}/legal-theories", headers=headers)
    assert response.status_code == 200
    theories = response.json()
    assert len(theories) == 1
    theory = theories[0]

    assert theory["theory_name"] == "Contract formation/performance through the conduct of the parties"
    assert theory["supporting_facts"] or theory["contradicting_facts"]
    assert theory["alternative_explanations"]
    assert theory["evidence_gaps"]  # unsigned draft -> a signature evidence gap

    # The fail-closed contract: no verified legal source exists in this test
    # database, so no theory may ever be labeled legal_theory here.
    assert theory["classification"] == "counsel_hypothesis"
    assert theory["verified_legal_authority"] == []
    assert "not promoted to a legal theory" in theory["source_provenance"] or "insufficient" in theory["source_provenance"]


@pytest.mark.asyncio
async def test_workspace_a_cannot_run_legal_theories_for_workspace_b_case(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Legal Theory Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Legal Theory Org B")
    await db_session.commit()

    case_id = await _create_case(client, workspace_a.id)
    response = await client.post(
        f"/api/v1/legal/cases/{case_id}/legal-theories", headers={"X-Workspace-Id": str(workspace_b.id)}
    )
    assert response.status_code == 404
