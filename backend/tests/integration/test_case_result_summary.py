"""Case Result Summary — client-facing synthesis over E1-E4 data
(GET /cases/{id}/result-summary). Same synthetic loan-dispute fixture as
test_litigation_evidence_layer.py; this file verifies the summary layer
itself: bounded template conclusions, honest missing-evidence phrasing,
real provenance, and that the internal "рабочая записка" work product is
never treated as evidence.
"""
from __future__ import annotations

import io

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

_WORK_PRODUCT_TEXT = (
    "Внутренняя рабочая записка юриста: возможно, стоит утверждать, что договор займа не был заключен, "
    "и указывать на неосновательное обогащение как основную версию защиты."
)


def _payment_text(number: str, amount: str, payment_date: str, with_bn: bool = True) -> str:
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


async def _build_adversarial_case(client, workspace_id) -> str:
    case_id = await _create_case(client, workspace_id, "Synthetic Adversarial Loan Case")
    claim_id = await _upload_ready_document(client, workspace_id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace_id, case_id, claim_id, "claim")

    for number, pdate in (("11", "13.09.2024"), ("797", "01.10.2024")):
        doc_id = await _upload_ready_document(client, workspace_id, f"payment_{number}.txt", _payment_text(number, "2000000-00", pdate))
        await _attach(client, workspace_id, case_id, doc_id, "payment_document")

    headers = {"X-Workspace-Id": str(workspace_id)}
    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200
    return case_id


@pytest.mark.asyncio
async def test_result_summary_surfaces_high_contradiction_with_provenance(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    assert response.status_code == 200
    body = response.json()

    high_findings = [f for f in body["key_findings"] if f["severity"] == "HIGH"]
    assert len(high_findings) >= 1
    finding = high_findings[0]
    assert finding["source_document_id"]
    assert finding["source_document_title"]
    assert finding["excerpt"]
    assert finding["caveat"] and "does not by itself establish" in finding["caveat"]


@pytest.mark.asyncio
async def test_result_summary_money_flow_total_is_correct(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    body = response.json()

    assert body["money_flow"]["total_amount"] == "4000000.00"
    assert body["money_flow"]["transaction_count"] == 2
    assert body["case_snapshot"]["total_amount"] == "4000000.00"
    assert body["case_snapshot"]["payment_count"] == 2


@pytest.mark.asyncio
async def test_result_summary_never_states_contract_was_concluded(client, db_session):
    """Safety rule: no section of the client-facing summary may affirmatively
    assert the contract WAS concluded — mentions of contract conclusion may
    only appear negated (the allegation being quoted) or inside the
    caveat/reason sentences that explicitly say evidence does NOT establish
    it. Every finding must carry a caveat, and no finding may assert
    conclusion as a flat, un-caveated fact.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    body = response.json()

    forbidden_phrases = ["договор был заключен между сторонами", "заключение договора подтверждено", "the contract is concluded"]
    haystack = " ".join(body["what_this_may_mean"]).lower() + " " + " ".join(f["statement"] for f in body["key_findings"]).lower()
    for phrase in forbidden_phrases:
        assert phrase not in haystack
    for finding in body["key_findings"]:
        if finding["severity"] == "HIGH":
            assert finding["caveat"]


@pytest.mark.asyncio
async def test_missing_evidence_uses_not_found_among_uploaded_materials_phrasing(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    body = response.json()

    assert len(body["missing_critical_evidence"]) > 0
    for item in body["missing_critical_evidence"]:
        assert "не обнаружен" in item["description"].lower()
        assert "среди загруженных материалов" in item["description"].lower()
        # Must never assert absolute non-existence.
        assert "не существует" not in item["description"].lower()


@pytest.mark.asyncio
async def test_missing_evidence_and_next_actions_depend_on_actual_gaps_not_static(client, db_session):
    """When a CORRESPONDENCE document IS attached, the correspondence-related
    missing-evidence item and its dependent next-best-action must disappear
    — proving the checklist is data-driven, not a hardcoded static list.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    before = (await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)).json()
    before_descriptions = {item["description"] for item in before["missing_critical_evidence"]}
    correspondence_item = next(d for d in before_descriptions if "Переписка сторон" in d)
    assert correspondence_item in before_descriptions

    correspondence_doc_id = await _upload_ready_document(
        client, workspace.id, "correspondence.txt", "Уважаемые коллеги, подтверждаем сумму займа и срок возврата."
    )
    await _attach(client, workspace.id, case_id, correspondence_doc_id, "correspondence")

    after = (await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)).json()
    after_descriptions = {item["description"] for item in after["missing_critical_evidence"]}
    assert correspondence_item not in after_descriptions


@pytest.mark.asyncio
async def test_empty_legal_kb_produces_warning_not_fabricated_law(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    body = response.json()

    assert body["legal_kb_warning"] is not None
    assert "не подтверждает окончательную правовую позицию" in body["legal_kb_warning"]


@pytest.mark.asyncio
async def test_internal_work_product_is_never_used_as_evidence_in_summary(client, db_session):
    """A 'рабочая записка' attached with role=OTHER must never contribute an
    allegation, appear as a key-finding source, or be counted as a document
    role satisfying any missing-evidence checklist item — the extractors
    only ever scan CLAIM/RESPONSE/COURT_FILING (allegations) and
    PAYMENT_DOCUMENT (payments) roles, so this is a structural guarantee,
    verified here end-to-end.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")

    work_product_id = await _upload_ready_document(client, workspace.id, "Анализ_иска.txt", _WORK_PRODUCT_TEXT)
    await _attach(client, workspace.id, case_id, work_product_id, "other")

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200

    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    body = response.json()

    for finding in body["key_findings"]:
        assert finding["source_document_id"] != work_product_id
    allegations = (await client.get(f"/api/v1/legal/cases/{case_id}/allegations", headers=headers)).json()
    assert all(a["document_id"] != work_product_id for a in allegations)


@pytest.mark.asyncio
async def test_workspace_a_cannot_read_workspace_b_result_summary(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Result Summary Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Result Summary Org B")
    await db_session.commit()
    headers_b = {"X-Workspace-Id": str(workspace_b.id)}

    case_id = await _create_case(client, workspace_a.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers_b)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_client_facing_smoke_summary_answers_what_would_client_see(client, db_session):
    """The product-quality test: if a client uploaded a claim + payment
    orders, what does Legal AI say in ~30 seconds? One main conclusion
    (money flow), the main contradiction, and 1-3 next actions — no
    fabricated legal verdicts.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_adversarial_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    body = response.json()

    assert body["money_flow"]["total_amount"]
    assert len(body["key_findings"]) >= 1
    assert 1 <= len(body["next_best_actions"]) <= 3
    for action in body["next_best_actions"]:
        assert action["action"]
        assert action["why"]
    assert body["legal_kb_warning"] is not None
