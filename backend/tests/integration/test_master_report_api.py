"""Master Case Report — full API integration test. Synthetic fixture only,
deliberately a DIFFERENT fact pattern (different party names, amounts,
dates, bank count) from the real Ledovyi Service v. BS Energo Region case
this feature was benchmarked against — proves the reasoning generalizes
rather than being hardcoded (§25 of the task brief).
"""
from __future__ import annotations

import io

import pytest

from tests.security.auth_factories import make_org_and_workspace


async def _create_case(client, workspace_id, title="Synthetic Master Report Case", client_name=None, counterparty_name=None):
    body = {"title": title}
    if client_name:
        body["client_name"] = client_name
    if counterparty_name:
        body["counterparty_name"] = counterparty_name
    response = await client.post("/api/v1/legal/cases", json=body, headers={"X-Workspace-Id": str(workspace_id)})
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


# Deliberately different from the real case: a "services financing" dispute,
# 4 payments (not 5), 2 banks (not 3), different amounts/dates/wording.
_CLAIM_TEXT = (
    "Истец перечислил Ответчику денежные средства в общем размере 4 400 000 руб. "
    "В устном порядке между сторонами шли переговоры о заключении договора займа. "
    "Истец был введен в заблуждение и вышеуказанные перечисления были совершены ошибочно. "
    "Впоследствии договор процентного займа не был заключен сторонами."
)


def _payment_text(number: str, amount: str, payment_date: str) -> str:
    return (
        f'ПЛАТЁЖНОЕ ПОРУЧЕНИЕ № {number} {payment_date}\n'
        f'Сумма {amount}\n'
        f'ООО "СИНТЕТИК ПЛЕЙНТИФФ"\n'
        f'Плательщик\n'
        f'ООО "СИНТЕТИК ДИФЕНДАНТ"\n'
        f'Получатель\n'
        f'Назначение платежа Перечисление средств по договору процентного займа от 05.02.2025г. НДС не облагается.\n'
        f'Исполнено {payment_date}\n'
    )


_CONTRACT_A = (
    "Договор процентного займа от 05.02.2025. Займодавец передает Заемщику 2 000 000 рублей. "
    "Процентная ставка составляет 8 процентов годовых. "
    "Договор считается заключенным с момента поступления денежных средств на расчетный счет Заемщика."
)
_CONTRACT_B_DRAFT = (
    "Проект договора процентного займа от 05.02.2025 (не подписан). Займодавец передает Заемщику 4 400 000 рублей. "
    "Договор считается заключенным с момента поступления денежных средств."
)


async def _build_synthetic_case(client, workspace_id) -> str:
    case_id = await _create_case(
        client, workspace_id, "Synthetic Financing Dispute", client_name="ООО «Синтетик Дифендант»"
    )
    claim_id = await _upload_ready_document(client, workspace_id, "claim.txt", _CLAIM_TEXT)
    await _attach(client, workspace_id, case_id, claim_id, "claim")

    for number, pdate in (("101", "10.02.2025"), ("102", "01.05.2025"), ("103", "15.08.2025"), ("104", "20.11.2025")):
        doc_id = await _upload_ready_document(client, workspace_id, f"payment_{number}.txt", _payment_text(number, "1100000-00", pdate))
        await _attach(client, workspace_id, case_id, doc_id, "payment_document")

    contract_a_id = await _upload_ready_document(client, workspace_id, "contract_a.txt", _CONTRACT_A)
    await _attach(client, workspace_id, case_id, contract_a_id, "contract")
    contract_b_id = await _upload_ready_document(client, workspace_id, "contract_b_draft.txt", _CONTRACT_B_DRAFT)
    await _attach(client, workspace_id, case_id, contract_b_id, "contract")

    headers = {"X-Workspace-Id": str(workspace_id)}
    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200
    return case_id


@pytest.mark.asyncio
async def test_master_report_surfaces_claim_contradiction_and_payment_pattern_on_synthetic_case(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    assert response.status_code == 200
    body = response.json()

    categories = {f["category"] for f in body["findings"]}
    # §23.4: the mistake-vs-negotiation tension must be found without any
    # case-specific code — this proves detect_claim_theory_tensions() generalized.
    assert "claim_contradiction" in categories
    assert "payment_pattern" in categories  # 4 payments over ~9 months
    assert "contract_mismatch" in categories  # 2 000 000 / 4 400 000 vs actual 4 400 000

    # §23.4: every finding carries provenance.
    for f in body["findings"]:
        if f["category"] in ("claim_contradiction", "payment_pattern", "contract_mismatch", "contract_formation"):
            assert f["confidence"]  # never blank

    # §23.9: missing evidence is clearly labelled, not silently omitted.
    evidence_gap_findings = [f for f in body["findings"] if f["category"] == "evidence_gap"]
    assert len(evidence_gap_findings) > 0
    for f in evidence_gap_findings:
        assert "не обнаруж" in f["statement"].lower() or "not" in f["statement"].lower()


@pytest.mark.asyncio
async def test_master_report_never_states_contract_concluded_or_not(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    body = response.json()

    haystack = " ".join(f["statement"] + " " + (f["caveat"] or "") for f in body["findings"]).lower()
    assert "the contract is concluded" not in haystack
    assert "the contract was not concluded" not in haystack
    assert "договор заключен между сторонами" not in haystack


@pytest.mark.asyncio
async def test_master_report_contract_mismatch_is_neutral_not_one_sided(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    body = response.json()

    mismatch = next(f for f in body["findings"] if f["category"] == "contract_mismatch")
    assert mismatch["helps_side"] == "neutral"
    assert mismatch["hurts_side"] == "neutral"


@pytest.mark.asyncio
async def test_master_report_one_pager_is_populated(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    body = response.json()

    one_pager = body["one_pager"]
    assert one_pager["money_at_stake"] == "4400000.00"
    assert len(one_pager["top_arguments"]) > 0 or len(one_pager["top_risks"]) > 0


@pytest.mark.asyncio
async def test_master_report_court_scenarios_carry_strategic_label_not_probability(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    body = response.json()

    assert len(body["court_scenarios"]) >= 2
    for s in body["court_scenarios"]:
        assert s["label"] == "STRATEGIC SCENARIO — NOT A COURT PREDICTION"
        assert "%" not in s["scenario"]


@pytest.mark.asyncio
async def test_master_report_works_with_partial_case_data(client, db_session):
    """§23.15: a case with only a Case row and no attached documents must
    not error — everything degrades to empty lists / honest gaps.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id, "Empty Case")
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["findings"] == [] or isinstance(body["findings"], list)
    assert body["money_flow"]["transaction_count"] == 0


@pytest.mark.asyncio
async def test_master_report_no_duplicate_finding_ids(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    ids = [f["id"] for f in response.json()["findings"]]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_master_report_deterministic_money_total_matches_money_flow_endpoint(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    report_response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    money_flow_response = await client.get(f"/api/v1/legal/cases/{case_id}/money-flow", headers=headers)

    assert report_response.json()["money_flow"]["total_amount"] == money_flow_response.json()["total_amount"] == "4400000.00"


@pytest.mark.asyncio
async def test_master_report_legal_kb_warning_present_when_kb_empty(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _build_synthetic_case(client, workspace.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    assert response.json()["legal_kb_warning"] is not None  # honest — test DB has no verified law


_INTEREST_TABLE_TEXT = (
    "\nРасчет процентов за пользование чужими денежными средствами:\n"
    "1 100 000 15.02.2025 01.04.2025 45 | 12% | 365 16 273,97\n"
)
_DEMAND_TEXT = (
    "Досудебное требование\n"
    "Представитель ООО «Синтетик Плейнтифф»\n"
    "по доверенности\n01.03.2025\n\n"
    "Отчет сформирован официальным сайтом Почты России 15 марта 2025 в 09:00\n"
    "Отчет об отслеживании отправления с почтовым идентификатором 30099999999999\n"
    "05 марта 2025, 09:30 Вручено извещение 220000, Минск\n"
    "20 марта 2025, 00:00 Срок хранения истек. Выслано обратно отправителю 220000, Минск\n"
)


@pytest.mark.asyncio
async def test_master_report_surfaces_interest_table_notice_and_timing_synthesis(client, db_session):
    """Parts 2/3/4/5b end-to-end: a per-installment interest table, a
    returned pre-suit demand, and the resulting timing synthesis — a
    deliberately different fact pattern (dates/amounts/company names) from
    the real case this feature was benchmarked against.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id, "Synthetic Timing Case")
    claim_id = await _upload_ready_document(client, workspace.id, "claim.txt", _CLAIM_TEXT + _INTEREST_TABLE_TEXT)
    await _attach(client, workspace.id, case_id, claim_id, "claim")
    demand_id = await _upload_ready_document(client, workspace.id, "demand.txt", _DEMAND_TEXT)
    await _attach(client, workspace.id, case_id, demand_id, "correspondence")

    analyze = await client.post(f"/api/v1/legal/cases/{case_id}/analyze", headers=headers)
    assert analyze.status_code == 200

    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers)
    assert response.status_code == 200
    findings = response.json()["findings"]
    categories = {f["category"] for f in findings}

    assert "interest_calculation" in categories
    table_finding = next(f for f in findings if f["id"] == "interest_calculation:table")
    assert "1 per-installment row(s)" in table_finding["statement"]

    notice_finding = next(f for f in findings if f["id"] == "notice_timeline:demand")
    assert notice_finding["category"] == "procedural"
    assert "returned" in notice_finding["statement"].lower()

    timing_findings = [f for f in findings if f["category"] == "timing"]
    assert len(timing_findings) >= 2
    assert {f["id"].split(":")[1] for f in timing_findings} >= {"interest_before_demand", "demand_not_confirmed_received"}

    synthesis_findings = [f for f in findings if f["category"] == "synthesis"]
    assert any(f["id"] == "synthesis:timing" for f in synthesis_findings)
    timing_synthesis = next(f for f in synthesis_findings if f["id"] == "synthesis:timing")
    assert set(timing_synthesis["synthesizes"]) == {f["id"] for f in timing_findings}


@pytest.mark.asyncio
async def test_master_report_workspace_isolation(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Master Report Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Master Report Org B")
    await db_session.commit()
    headers_b = {"X-Workspace-Id": str(workspace_b.id)}

    case_id = await _create_case(client, workspace_a.id)
    response = await client.get(f"/api/v1/legal/cases/{case_id}/master-report", headers=headers_b)
    assert response.status_code == 404
