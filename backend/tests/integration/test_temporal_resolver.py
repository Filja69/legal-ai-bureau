"""TemporalLawResolver — LEGAL-DATABASE.md §3, Phase 2 brief §9-10.

Case A from the brief: article 309 has two redactions —
  v1: [2024-01-01, 2025-01-01)
  v2: [2025-01-01, NULL)  (currently in force)
Query 2024-12-01 -> v1. Query 2025-02-01 -> v2. Plus boundary, missing,
future, and invalid-interval edge cases, and the DB-level overlap guarantee.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.legal_knowledge.temporal_resolver import InvalidTemporalIntervalError, TemporalLawResolver
from app.models.legal_knowledge import Law, LawVersion, LegalDocument, LegalDocumentType


async def _make_law(db_session, short_name: str = "ГК РФ") -> Law:
    document = LegalDocument(title=short_name, document_type=LegalDocumentType.CODE)
    db_session.add(document)
    await db_session.flush()
    law = Law(document_id=document.id, short_name=short_name, full_name="Гражданский кодекс РФ")
    db_session.add(law)
    await db_session.flush()
    return law


async def _make_version(db_session, law: Law, article: str, text: str, valid_from: date, valid_to: date | None, clause: str | None = None):
    version = LawVersion(
        law_id=law.id, article_number=article, clause_number=clause, text=text,
        valid_from=valid_from, valid_to=valid_to,
    )
    db_session.add(version)
    await db_session.flush()
    return version


@pytest.mark.asyncio
async def test_case_a_query_before_amendment_resolves_v1(db_session):
    law = await _make_law(db_session)
    v1 = await _make_version(db_session, law, "309", "v1 text", date(2024, 1, 1), date(2025, 1, 1))
    await _make_version(db_session, law, "309", "v2 text", date(2025, 1, 1), None)
    await db_session.commit()

    resolver = TemporalLawResolver(db_session)
    resolved = await resolver.resolve_article("ГК РФ", "309", effective_at=date(2024, 12, 1))

    assert resolved is not None
    assert resolved.law_version.id == v1.id
    assert resolved.law_version.text == "v1 text"
    assert resolved.is_currently_in_force is False


@pytest.mark.asyncio
async def test_case_a_query_after_amendment_resolves_v2(db_session):
    law = await _make_law(db_session)
    await _make_version(db_session, law, "309", "v1 text", date(2024, 1, 1), date(2025, 1, 1))
    v2 = await _make_version(db_session, law, "309", "v2 text", date(2025, 1, 1), None)
    await db_session.commit()

    resolver = TemporalLawResolver(db_session)
    resolved = await resolver.resolve_article("ГК РФ", "309", effective_at=date(2025, 2, 1))

    assert resolved is not None
    assert resolved.law_version.id == v2.id
    assert resolved.is_currently_in_force is True


@pytest.mark.asyncio
async def test_resolve_article_defaults_to_today(db_session):
    law = await _make_law(db_session)
    await _make_version(db_session, law, "1", "old", date(2000, 1, 1), date(2020, 1, 1))
    current = await _make_version(db_session, law, "1", "current", date(2020, 1, 1), None)
    await db_session.commit()

    resolver = TemporalLawResolver(db_session)
    resolved = await resolver.resolve_article("ГК РФ", "1")

    assert resolved is not None
    assert resolved.law_version.id == current.id


class TestBoundaryDates:
    @pytest.mark.asyncio
    async def test_query_exactly_on_valid_from_is_included(self, db_session):
        law = await _make_law(db_session)
        v = await _make_version(db_session, law, "309", "text", date(2025, 1, 1), None)
        await db_session.commit()

        resolver = TemporalLawResolver(db_session)
        resolved = await resolver.resolve_article("ГК РФ", "309", effective_at=date(2025, 1, 1))

        assert resolved is not None
        assert resolved.law_version.id == v.id

    @pytest.mark.asyncio
    async def test_query_exactly_on_valid_to_belongs_to_next_version(self, db_session):
        # [)-semantics: valid_to is exclusive, so the boundary date belongs to
        # whichever version starts there, never both.
        law = await _make_law(db_session)
        v1 = await _make_version(db_session, law, "309", "v1", date(2024, 1, 1), date(2025, 1, 1))
        v2 = await _make_version(db_session, law, "309", "v2", date(2025, 1, 1), None)
        await db_session.commit()

        resolver = TemporalLawResolver(db_session)
        resolved = await resolver.resolve_article("ГК РФ", "309", effective_at=date(2025, 1, 1))

        assert resolved.law_version.id == v2.id
        assert resolved.law_version.id != v1.id

    @pytest.mark.asyncio
    async def test_query_one_day_before_valid_to_is_still_old_version(self, db_session):
        law = await _make_law(db_session)
        v1 = await _make_version(db_session, law, "309", "v1", date(2024, 1, 1), date(2025, 1, 1))
        await _make_version(db_session, law, "309", "v2", date(2025, 1, 1), None)
        await db_session.commit()

        resolver = TemporalLawResolver(db_session)
        resolved = await resolver.resolve_article("ГК РФ", "309", effective_at=date(2024, 12, 31))

        assert resolved.law_version.id == v1.id


class TestOverlapPrevention:
    @pytest.mark.asyncio
    async def test_overlapping_versions_of_same_article_are_rejected_by_db(self, db_session):
        law = await _make_law(db_session)
        await _make_version(db_session, law, "309", "v1", date(2024, 1, 1), date(2025, 1, 1))
        await db_session.commit()

        # Overlaps [2024-06-01, 2025-06-01) with the existing [2024-01-01, 2025-01-01)
        # — Postgres checks EXCLUDE constraints per-statement, so this raises on
        # the flush inside _make_version, not on a later explicit commit.
        with pytest.raises(IntegrityError):
            await _make_version(db_session, law, "309", "overlapping", date(2024, 6, 1), date(2025, 6, 1))
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_open_ended_version_overlapping_a_closed_one_is_rejected(self, db_session):
        law = await _make_law(db_session)
        await _make_version(db_session, law, "1", "closed", date(2020, 1, 1), date(2022, 1, 1))
        await db_session.commit()

        # Open-ended version starting before the closed one ends -> overlaps.
        with pytest.raises(IntegrityError):
            await _make_version(db_session, law, "1", "open-ended", date(2021, 1, 1), None)
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_adjacent_non_overlapping_versions_are_allowed(self, db_session):
        law = await _make_law(db_session)
        await _make_version(db_session, law, "1", "v1", date(2020, 1, 1), date(2022, 1, 1))
        await _make_version(db_session, law, "1", "v2", date(2022, 1, 1), None)
        # Should not raise — [)-adjacent intervals never overlap.
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_different_articles_of_same_law_may_overlap_freely(self, db_session):
        law = await _make_law(db_session)
        await _make_version(db_session, law, "1", "art1", date(2020, 1, 1), None)
        await _make_version(db_session, law, "2", "art2", date(2020, 1, 1), None)
        # Different article_number -> not the same norm -> no conflict.
        await db_session.commit()


class TestMissingAndFutureVersions:
    @pytest.mark.asyncio
    async def test_missing_article_resolves_to_none(self, db_session):
        law = await _make_law(db_session)
        await _make_version(db_session, law, "309", "text", date(2024, 1, 1), None)
        await db_session.commit()

        resolver = TemporalLawResolver(db_session)
        resolved = await resolver.resolve_article("ГК РФ", "999", effective_at=date(2025, 1, 1))

        assert resolved is None

    @pytest.mark.asyncio
    async def test_query_before_any_version_existed_resolves_to_none(self, db_session):
        law = await _make_law(db_session)
        await _make_version(db_session, law, "309", "text", date(2024, 1, 1), None)
        await db_session.commit()

        resolver = TemporalLawResolver(db_session)
        resolved = await resolver.resolve_article("ГК РФ", "309", effective_at=date(2020, 1, 1))

        assert resolved is None

    @pytest.mark.asyncio
    async def test_unknown_code_resolves_to_none(self, db_session):
        resolver = TemporalLawResolver(db_session)
        resolved = await resolver.resolve_article("Несуществующий кодекс", "1", effective_at=date(2025, 1, 1))
        assert resolved is None


class TestInvalidIntervals:
    def test_valid_to_before_valid_from_is_rejected(self):
        with pytest.raises(InvalidTemporalIntervalError):
            TemporalLawResolver.validate_interval(date(2025, 1, 1), date(2024, 1, 1))

    def test_valid_to_equal_to_valid_from_is_rejected(self):
        with pytest.raises(InvalidTemporalIntervalError):
            TemporalLawResolver.validate_interval(date(2025, 1, 1), date(2025, 1, 1))

    def test_open_ended_interval_is_valid(self):
        TemporalLawResolver.validate_interval(date(2025, 1, 1), None)

    def test_forward_interval_is_valid(self):
        TemporalLawResolver.validate_interval(date(2024, 1, 1), date(2025, 1, 1))


@pytest.mark.asyncio
async def test_resolve_law_returns_all_articles_in_force_at_date(db_session):
    law = await _make_law(db_session)
    art1 = await _make_version(db_session, law, "1", "art1 v1", date(2020, 1, 1), date(2022, 1, 1))
    art1_v2 = await _make_version(db_session, law, "1", "art1 v2", date(2022, 1, 1), None)
    art2 = await _make_version(db_session, law, "2", "art2", date(2020, 1, 1), None)
    await db_session.commit()

    resolver = TemporalLawResolver(db_session)
    resolved = await resolver.resolve_law(law.id, effective_at=date(2023, 1, 1))

    resolved_ids = {r.law_version.id for r in resolved}
    assert resolved_ids == {art1_v2.id, art2.id}
    assert art1.id not in resolved_ids
