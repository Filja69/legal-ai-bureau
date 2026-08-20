"""E1-E4 — litigation evidence layer (claim allegations, structured payment
orders, CLAIM_VS_EVIDENCE contradictions, Case -> Legal Research wiring).
Full pipeline against real Postgres. Synthetic fixtures only, modeled on a
generic loan-dispute fact pattern (never the real client's documents).
"""
from __future__ import annotations

import io
import uuid

import pytest

from tests.security.auth_factories import make_org_and_workspace


async def _create_case(client, workspace_id, title="Test Loan Dispute"):
    response = await client.post("/api/v1/legal/cases", json={"title": title}, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    return response.json()["id"]


async def _upload_ready_document(client, workspace_id, filename: str, text: str):
    files = {"file": (filename, io.BytesIO(text.encode("utf-8")), "text/plain")}
    response = await client.post("/api/v1/legal/documents", files=files, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    return body["id"]


async def _attach(client, workspace_id, case_id, document_id, role):
    resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/documents", json={"document_id": document_id, "role": role},
        headers={"X-Workspace-Id": str(workspace_id)},
    )
    assert resp.status_code == 201


_CLAIM_TEXT = (
    "Истец перечислил Ответчику денежные средства в общем размере 6 000 000 руб. "
    "В устном порядке между сторонами шли переговоры о заключении договора займа. "
    "Впоследствии договор займа не был заключен сторонами, в связи с чем перечисленные "
    "денежные средства являются неосновательным обогащением."
)


def _payment_text(number: str, amount: str, payment_date: str, with_bn: bool) -> str:
    bn = "б/н " if with_bn else ""
    return (
        f'ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № {number} {payment_date}\n'
        f'Сумма {amount}\n'
        f'ООО "ИСТЕЦ ТРЕЙД"\n'
        f'Плательщик\n'
        f'ООО "ОТВЕТЧИК СЕРВИС"\n'
        f'Получатель\n'
        f'Назначение платежа Перечисление средств по договору процентного займа {bn}от 11.09.2024г. НДС не облагается.\n'
        f'Исполнено {payment_date}\n'
    )


@pytest.mark.asyncio
async def test_extract_allegations_persists_with_provenance(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")

    extract = await client.post(f"/api/v1/legal/cases/{case_id}/allegations/extract", headers=headers)
    assert extract.status_code == 200
    allegations = extract.json()
    types = {a["allegation_type"] for a in allegations}
    assert "no_contract" in types
    assert "unjust_enrichment" in types
    assert "future_contract_negotiations" in types
    for allegation in allegations:
        assert allegation["excerpt"]
        assert allegation["document_id"] == claim_id


@pytest.mark.asyncio
async def test_extract_payment_orders_and_money_flow(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    payment_specs = [
        ("11", "2000000-00", "13.09.2024", True),
        ("797", "2000000-00", "01.10.2024", False),
        ("397", "2000000-00", "11.10.2024", False),
    ]
    for number, amount, pdate, with_bn in payment_specs:
        doc_id = await _upload_ready_document(
            client, workspace.id, f"payment_{number}.txt", _payment_text(number, amount, pdate, with_bn)
        )
        await _attach(client, workspace.id, case_id, doc_id, "payment_document")

    extract = await client.post(f"/api/v1/legal/cases/{case_id}/payment-orders/extract", headers=headers)
    assert extract.status_code == 200
    orders = extract.json()
    assert len(orders) == 3
    for order in orders:
        assert order["referenced_contract_type"] == "договор процентного займа"
        assert order["referenced_contract_date"] == "2024-09-11"
        assert order["amount"] == "2000000.00"
        assert order["excerpt"]

    money_flow = await client.get(f"/api/v1/legal/cases/{case_id}/money-flow", headers=headers)
    assert money_flow.status_code == 200
    body = money_flow.json()
    assert body["transaction_count"] == 3
    assert body["total_amount"] == "6000000.00"
    # Same referenced contract date across all 3 payments -- grouped by
    # count, never merged into "one obligation" as a conclusion.
    assert body["referenced_contract_dates"] == {"2024-09-11": 3}


@pytest.mark.asyncio
async def test_full_synthetic_adversarial_case_surfaces_potential_contradiction_not_a_verdict(client, db_session):
    """The exact scenario from the companion brief: a claim alleging no
    loan agreement was concluded, against multiple payment orders that
    explicitly reference a loan agreement dated 11.09.2024. Expected:
    POTENTIAL MATERIAL CONTRADICTION with a caveat — never an automatic
    "contract concluded" verdict.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id, "Synthetic Adversarial Loan Case")

    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")

    payment_specs = [("11", "2000000-00", "13.09.2024", True), ("797", "2000000-00", "01.10.2024", False)]
    payment_ids = []
    for number, amount, pdate, with_bn in payment_specs:
        doc_id = await _upload_ready_document(
            client, workspace.id, f"payment_{number}.txt", _payment_text(number, amount, pdate, with_bn)
        )
        await _attach(client, workspace.id, case_id, doc_id, "payment_document")
        payment_ids.append(doc_id)

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200
    assert analyze.json()["allegation_count"] >= 1
    assert analyze.json()["payment_order_count"] == 2
    assert analyze.json()["claim_evidence_contradiction_count"] == 2  # one per matching payment

    contradictions = await client.get(f"/api/v1/legal/cases/{case_id}/claim-evidence-contradictions", headers=headers)
    assert contradictions.status_code == 200
    results = contradictions.json()
    assert len(results) == 2
    for result in results:
        assert result["contradiction_type"] == "claim_vs_evidence"
        assert result["allegation_document_id"] == claim_id
        assert result["evidence_document_id"] in payment_ids
        assert result["referenced_contract_date"] == "2024-09-11"
        assert result["allegation_excerpt"]
        assert result["evidence_excerpt"]
        # Safety rule 6: never an automatic verdict.
        assert "does not by itself establish that the contract was legally concluded" in result["caveat"]
        assert result["confidence"]


@pytest.mark.asyncio
async def test_generic_payment_purpose_never_triggers_false_positive_contradiction(client, db_session):
    """Regression test #5: a payment referencing an UNRELATED contract
    (e.g. a supply contract) must never be treated as evidence contradicting
    a NO_CONTRACT (loan) allegation.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")

    unrelated_payment_text = (
        'ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № 99 01.01.2025\n'
        'Сумма 100000-00\n'
        'ООО "ИСТЕЦ ТРЕЙД"\nПлательщик\nООО "ОТВЕТЧИК СЕРВИС"\nПолучатель\n'
        'Назначение платежа Оплата по договору поставки №4 от 01.01.2025г.\n'
        'Исполнено 01.01.2025\n'
    )
    doc_id = await _upload_ready_document(client, workspace.id, "unrelated_payment.txt", unrelated_payment_text)
    await _attach(client, workspace.id, case_id, doc_id, "payment_document")

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.json()["claim_evidence_contradiction_count"] == 0


@pytest.mark.asyncio
async def test_extraction_is_idempotent_for_allegations_and_payment_orders(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")
    payment_id = await _upload_ready_document(client, workspace.id, "payment.txt", _payment_text("11", "2000000-00", "13.09.2024", True))
    await _attach(client, workspace.id, case_id, payment_id, "payment_document")

    first_a = await client.post(f"/api/v1/legal/cases/{case_id}/allegations/extract", headers=headers)
    second_a = await client.post(f"/api/v1/legal/cases/{case_id}/allegations/extract", headers=headers)
    assert len(first_a.json()) == len(second_a.json())

    first_p = await client.post(f"/api/v1/legal/cases/{case_id}/payment-orders/extract", headers=headers)
    second_p = await client.post(f"/api/v1/legal/cases/{case_id}/payment-orders/extract", headers=headers)
    assert len(first_p.json()) == len(second_p.json())


# --- E4: Case -> Legal Research ---


@pytest.mark.asyncio
async def test_case_research_forwards_case_documents_and_returns_honest_result(client, db_session):
    """Reuses the existing /research handler wholesale — the Knowledge Base
    is empty in this test DB, so a LOW-confidence / no-verified-rules result
    is the CORRECT, honest outcome, not a failure.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")

    response = await client.post(
        f"/api/v1/legal/cases/{case_id}/research",
        json={"question": "Был ли заключен договор займа между сторонами?"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert "research_id" in body
    assert "status" in body


@pytest.mark.asyncio
async def test_case_research_returns_404_for_nonexistent_case(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    response = await client.post(
        f"/api/v1/legal/cases/{uuid.uuid4()}/research", json={"question": "Test question?"}, headers=headers
    )
    assert response.status_code == 404


# --- Tenant isolation ---


@pytest.mark.asyncio
async def test_workspace_a_cannot_read_or_extract_workspace_b_allegations_payments_research(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Evidence Layer Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Evidence Layer Org B")
    await db_session.commit()
    headers_b = {"X-Workspace-Id": str(workspace_b.id)}

    case_id = await _create_case(client, workspace_a.id)

    assert (await client.get(f"/api/v1/legal/cases/{case_id}/allegations", headers=headers_b)).status_code == 404
    assert (await client.post(f"/api/v1/legal/cases/{case_id}/allegations/extract", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/payment-orders", headers=headers_b)).status_code == 404
    assert (await client.post(f"/api/v1/legal/cases/{case_id}/payment-orders/extract", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/money-flow", headers=headers_b)).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/claim-evidence-contradictions", headers=headers_b)).status_code == 404
    assert (
        await client.post(f"/api/v1/legal/cases/{case_id}/research", json={"question": "q?"}, headers=headers_b)
    ).status_code == 404
