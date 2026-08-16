"""TemporalLawResolver — "what did the law say on date X" (LEGAL-DATABASE.md §3,
Phase 2 brief §9-10). The single place that resolves a norm to the version that
was actually in force on a given date; nothing else in the codebase should
hand-roll this query.

Resolution rule: valid_from <= effective_at < valid_to (valid_to NULL = still
in force). The DB-level exclusion constraint added in migration
0002_legal_knowledge_infrastructure guarantees at most one row can ever match
for a given (law_id, article_number, clause_number) — see LawVersion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.legal_knowledge import Law, LawVersion


class InvalidTemporalIntervalError(Exception):
    """valid_from must be strictly before valid_to when valid_to is set."""


@dataclass
class ResolvedLawVersion:
    law_version: LawVersion
    is_currently_in_force: bool


class TemporalLawResolver:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_law(self, law_id, effective_at: date | None = None) -> list[ResolvedLawVersion]:
        """All article/clause versions of `law_id` in force on `effective_at`
        (defaults to today — "the version in force right now").
        """
        as_of = effective_at or date.today()
        stmt = select(LawVersion).where(
            LawVersion.law_id == law_id,
            LawVersion.valid_from <= as_of,
            (LawVersion.valid_to.is_(None)) | (LawVersion.valid_to > as_of),
        )
        result = await self._session.execute(stmt)
        return [
            ResolvedLawVersion(law_version=v, is_currently_in_force=v.valid_to is None)
            for v in result.scalars().all()
        ]

    async def resolve_article(
        self,
        code: str,
        article: str,
        clause: str | None = None,
        effective_at: date | None = None,
    ) -> ResolvedLawVersion | None:
        """Resolve a single article (optionally a clause within it) of a code
        (e.g. "ГК РФ") to the version in force on `effective_at` (default: today).
        """
        as_of = effective_at or date.today()
        stmt = (
            select(LawVersion)
            .join(Law, Law.id == LawVersion.law_id)
            .where(
                Law.short_name == code,
                LawVersion.article_number == article,
                LawVersion.valid_from <= as_of,
                (LawVersion.valid_to.is_(None)) | (LawVersion.valid_to > as_of),
            )
        )
        stmt = stmt.where(LawVersion.clause_number == clause) if clause is not None else stmt.where(LawVersion.clause_number.is_(None))
        result = await self._session.execute(stmt)
        version = result.scalars().first()
        if version is None:
            return None
        return ResolvedLawVersion(law_version=version, is_currently_in_force=version.valid_to is None)

    @staticmethod
    def validate_interval(valid_from: date, valid_to: date | None) -> None:
        """Application-level guard used by the ingestion pipeline *before* an
        insert is attempted — gives a clear error instead of a raw
        IntegrityError from the DB exclusion constraint for this specific
        (cheap, obviously-wrong) case.
        """
        if valid_to is not None and valid_to <= valid_from:
            raise InvalidTemporalIntervalError(
                f"valid_to ({valid_to}) must be strictly after valid_from ({valid_from})"
            )
