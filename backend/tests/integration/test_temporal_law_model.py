"""Temporal law versioning — LEGAL-DATABASE.md §3. A norm's text is only ever
reachable through a dated LawVersion row, never a bare mutable field.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.legal_knowledge import Law, LawVersion, LegalDocument, LegalDocumentType


@pytest.mark.asyncio
async def test_law_version_resolves_correct_redaction_for_event_date(db_session):
    document = LegalDocument(title="ГК РФ", document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()

    law = Law(document_id=document.id, short_name="ГК РФ", full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()

    old_version = LawVersion(
        law_id=law.id, article_number="309", text="Old redaction text",
        valid_from=date(2020, 1, 1), valid_to=date(2024, 1, 1),
    )
    new_version = LawVersion(
        law_id=law.id, article_number="309", text="New redaction text",
        valid_from=date(2024, 1, 1), valid_to=None,
    )
    db_session.add_all([old_version, new_version])
    await db_session.flush()

    event_date = date(2023, 6, 1)
    stmt = select(LawVersion).where(
        LawVersion.article_number == "309",
        LawVersion.valid_from <= event_date,
        (LawVersion.valid_to.is_(None)) | (LawVersion.valid_to > event_date),
    )
    result = await db_session.execute(stmt)
    resolved = result.scalars().one()

    assert resolved.text == "Old redaction text"


@pytest.mark.asyncio
async def test_currently_effective_version_has_null_valid_to(db_session):
    document = LegalDocument(title="ГК РФ", document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()
    law = Law(document_id=document.id, short_name="ГК РФ", full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()

    current = LawVersion(law_id=law.id, article_number="1", text="Current text", valid_from=date(2024, 1, 1), valid_to=None)
    db_session.add(current)
    await db_session.flush()

    assert current.valid_to is None
