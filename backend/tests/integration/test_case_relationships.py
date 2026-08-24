"""Case Intelligence — party relationships, hypothesis register, related
litigation. Full pipeline against real Postgres. Synthetic fixtures only —
these hypothesis wordings are inspired by the real Ledoviy Service v. BS
Energo Region matter's counsel-provided hypotheses but never use the real
parties' actual names/documents; see conversation history for the "no real
client data in production/tests" rule established throughout this project.
"""
from __future__ import annotations

import uuid

import pytest

from tests.security.auth_factories import make_org_and_workspace


async def _create_case(client, workspace_id, title="Synthetic Relationship Test Case"):
    response = await client.post("/api/v1/legal/cases", json={"title": title}, headers={"X-Workspace-Id": str(workspace_id)})
    assert response.status_code == 201
    return response.json()["id"]


async def _add_party(client, workspace_id, case_id, name, party_type, procedural_role):
    resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/parties",
        json={"name": name, "party_type": party_type, "procedural_role": procedural_role},
        headers={"X-Workspace-Id": str(workspace_id)},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_add_and_list_party_relationship_with_provenance(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    person_id = await _add_party(client, workspace.id, case_id, "Иванов И.И.", "individual", "unknown")
    entity_id = await _add_party(client, workspace.id, case_id, "ООО «Тестовая Компания»", "organization", "defendant")

    create_resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/party-relationships",
        json={
            "subject_party_id": person_id, "related_party_id": entity_id, "relationship_type": "member",
            "start_date": "2024-06-01", "verification_status": "unverified",
            "source_excerpt": "Согласно выписке из ЕГРЮЛ, Иванов И.И. является участником общества с 01.06.2024.",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert body["relationship_type"] == "member"
    assert body["verification_status"] == "unverified"  # never auto-upgraded

    list_resp = await client.get(f"/api/v1/legal/cases/{case_id}/party-relationships", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_relationship_requires_parties_to_belong_to_the_same_case(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    person_id = await _add_party(client, workspace.id, case_id, "Иванов И.И.", "individual", "unknown")

    resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/party-relationships",
        json={"subject_party_id": person_id, "related_party_id": str(uuid.uuid4()), "relationship_type": "director"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_and_list_hypothesis_never_auto_promoted_to_fact(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    person_id = await _add_party(client, workspace.id, case_id, "Иванов И.И.", "individual", "unknown")
    entity_id = await _add_party(client, workspace.id, case_id, "ООО «Тестовая Компания»", "organization", "defendant")
    rel_resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/party-relationships",
        json={"subject_party_id": person_id, "related_party_id": entity_id, "relationship_type": "member"},
        headers=headers,
    )
    relationship_id = rel_resp.json()["id"]

    create_resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/hypotheses",
        json={
            "category": "counsel_hypothesis",
            "statement": "Истец мог иметь доступ к корпоративной информации ответчика через данное лицо.",
            "required_verification": ["История ЕГРЮЛ", "Реестр участников", "Переписка о предоставлении информации"],
            "related_relationship_id": relationship_id,
            "source": "counsel",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["category"] == "counsel_hypothesis"

    list_resp = await client.get(f"/api/v1/legal/cases/{case_id}/hypotheses", headers=headers)
    hypotheses = list_resp.json()
    assert len(hypotheses) == 1
    assert hypotheses[0]["category"] == "counsel_hypothesis"  # exact category preserved, no automatic reclassification


@pytest.mark.asyncio
async def test_related_litigation_never_states_a_causal_claim(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    create_resp = await client.post(
        f"/api/v1/legal/cases/{case_id}/related-litigation",
        json={
            "court": "Арбитражный суд г. Москвы", "case_number": "А40-99999/2026",
            "parties_description": "Истец против третьего лица (иной спор)",
            "subject_matter": "Взыскание задолженности", "amount_in_dispute": "100000000.00",
            "note": "Со слов представителя истца.",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    body = create_resp.json()
    assert "А40-99999/2026" in body["contextual_note"]
    assert "не подтверждают, что оно стало причиной" in body["contextual_note"]  # correctly negated
    for forbidden in ("нуждается в деньгах", "иск подан из-за", "финансовое давление объясняет подачу"):
        assert forbidden not in body["contextual_note"]

    list_resp = await client.get(f"/api/v1/legal/cases/{case_id}/related-litigation", headers=headers)
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["contextual_note"] == body["contextual_note"]


@pytest.mark.asyncio
async def test_relationship_timeline_sync_is_idempotent_and_never_touches_fact_derived_events(client, db_session):
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    person_id = await _add_party(client, workspace.id, case_id, "Слепнев П.Б.", "individual", "unknown")
    entity_id = await _add_party(client, workspace.id, case_id, "ООО «БС ЭНЕРГО РЕГИОН — TEST»", "organization", "defendant")
    await client.post(
        f"/api/v1/legal/cases/{case_id}/party-relationships",
        json={
            "subject_party_id": person_id, "related_party_id": entity_id, "relationship_type": "member",
            "start_date": "2024-06-01", "end_date": "2025-01-01",
        },
        headers=headers,
    )

    first_sync = await client.post(f"/api/v1/legal/cases/{case_id}/party-relationships/sync-timeline", headers=headers)
    assert first_sync.status_code == 200
    events = first_sync.json()
    assert len(events) == 2  # one for start_date, one for end_date
    assert {e["event_type"] for e in events} == {"shareholder_change"}
    assert {e["event_date"] for e in events} == {"2024-06-01", "2025-01-01"}

    second_sync = await client.post(f"/api/v1/legal/cases/{case_id}/party-relationships/sync-timeline", headers=headers)
    assert len(second_sync.json()) == 2  # idempotent, not duplicated

    timeline_resp = await client.get(f"/api/v1/legal/cases/{case_id}/timeline", headers=headers)
    assert len(timeline_resp.json()) == 2  # no fact-derived events exist in this case, so this equals the relationship events


@pytest.mark.asyncio
async def test_result_summary_surfaces_relationship_with_timing_and_open_questions(client, db_session):
    """The exact scenario from the real matter's counsel hypothesis (director
    of claimant later becoming a member of defendant), fully synthetic.
    """
    _org, workspace = await make_org_and_workspace(db_session)
    await db_session.commit()
    headers = {"X-Workspace-Id": str(workspace.id)}

    case_id = await _create_case(client, workspace.id)
    person_id = await _add_party(client, workspace.id, case_id, "Директор Истца (синтетика)", "individual", "unknown")
    entity_id = await _add_party(client, workspace.id, case_id, "ООО «Ответчик — TEST»", "organization", "defendant")
    await client.post(
        f"/api/v1/legal/cases/{case_id}/party-relationships",
        json={
            "subject_party_id": person_id, "related_party_id": entity_id, "relationship_type": "member",
            "start_date": "2024-06-01", "verification_status": "unverified",
        },
        headers=headers,
    )

    response = await client.get(f"/api/v1/legal/cases/{case_id}/result-summary", headers=headers)
    assert response.status_code == 200
    findings = response.json()["party_relationship_findings"]
    assert len(findings) == 1
    finding = findings[0]
    assert finding["relationship_type"] == "member"
    assert "does not by itself establish actual knowledge" in finding["timing_note"] or finding["relationship_start"] == "2024-06-01"
    assert len(finding["what_is_still_needed"]) > 0
    for forbidden in ("установлено", "доказано", "заведомо знал"):
        assert forbidden not in finding["why_it_may_matter"].lower()


@pytest.mark.asyncio
async def test_workspace_isolation_across_all_new_endpoints(client, db_session):
    _org_a, workspace_a = await make_org_and_workspace(db_session, "Relationship Org A")
    _org_b, workspace_b = await make_org_and_workspace(db_session, "Relationship Org B")
    await db_session.commit()
    headers_b = {"X-Workspace-Id": str(workspace_b.id)}

    case_id = await _create_case(client, workspace_a.id)

    assert (await client.get(f"/api/v1/legal/cases/{case_id}/party-relationships", headers=headers_b)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/legal/cases/{case_id}/party-relationships",
            json={"subject_party_id": str(uuid.uuid4()), "related_party_id": str(uuid.uuid4()), "relationship_type": "director"},
            headers=headers_b,
        )
    ).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/hypotheses", headers=headers_b)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/legal/cases/{case_id}/hypotheses",
            json={"category": "counsel_hypothesis", "statement": "test"}, headers=headers_b,
        )
    ).status_code == 404
    assert (await client.get(f"/api/v1/legal/cases/{case_id}/related-litigation", headers=headers_b)).status_code == 404
    assert (
        await client.post(f"/api/v1/legal/cases/{case_id}/related-litigation", json={"case_number": "test"}, headers=headers_b)
    ).status_code == 404
    assert (await client.post(f"/api/v1/legal/cases/{case_id}/party-relationships/sync-timeline", headers=headers_b)).status_code == 404
