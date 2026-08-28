"""Case-Law Relevance (P2 §7) — deterministic fields (case identity, court
level, date) always come straight from the already citation-validated
`CourtDecision` row; the narrative dimensions are exercised end-to-end
against MockLLMProvider (never a live LLM in tests).
"""
from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from app.domains.legal_research.case_law_relevance import assess_case_law_relevance
from app.domains.legal_research.engine import LegalResearchEngine
from app.domains.legal_research.models import AuthorityLevel, ClaimImportance, ClaimVerificationStatus, LegalClaim, LegalIssue
from app.llm.base import LLMMessage
from app.llm.providers.mock_provider import MockLLMProvider
from app.llm.routing.gateway import LLMGateway
from app.models.case_law import Court, CourtDecision, CourtLevel
from app.models.legal_knowledge import LegalDocument, LegalDocumentType, LegalSource, SourceType


class _FixedRelevanceProvider:
    """P2 §12 validation — a real relevance judgment (weak similarity,
    or a decision that cuts against the theory) needs a provider that
    actually answers the schema, unlike MockLLMProvider's honest-empty
    default. Deterministic, no network — returns exactly the fixed
    response it was built with, regardless of the prompt.
    """

    name = "fixed-stub"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    async def structured_generate(
        self, messages: list[LLMMessage], *, response_schema: dict[str, Any], system: str | None = None,
        model: str | None = None, temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self._response


async def _seed_verified_decision(db_session, case_number: str) -> None:
    source = LegalSource(name="Official Court DB", type=SourceType.COURT, is_official=True)
    db_session.add(source)
    await db_session.flush()
    court = Court(name="Верховный Суд РФ", level=CourtLevel.SUPREME, jurisdiction="RU")
    db_session.add(court)
    await db_session.flush()
    document = LegalDocument(
        title=f"Решение по делу {case_number}", document_type=LegalDocumentType.COURT_DECISION, source_id=source.id,
    )
    db_session.add(document)
    await db_session.flush()
    decision = CourtDecision(
        document_id=document.id, court_id=court.id, case_number=case_number, decision_date="2019-06-01",
        claim_summary="Иск о взыскании долга по договору займа.",
        decision_summary="Иск удовлетворен, договор признан заключенным по факту исполнения.",
        legal_reasoning="Суд указал, что перечисление денежных средств является исполнением договора займа.",
        outcome="granted",
    )
    db_session.add(decision)
    await db_session.flush()


@pytest.mark.asyncio
async def test_relevance_assessed_only_for_verified_case_law_claims(db_session):
    await _seed_verified_decision(db_session, "А40-7777/2024")

    engine = LegalResearchEngine(db_session, LLMGateway(provider=MockLLMProvider()))
    issues = [LegalIssue(id="1", title="Заключение договора конклюдентными действиями", description="d", priority=1)]
    claims = [
        LegalClaim(
            claim="А40-7777/2024: ...", claim_type="case_law", importance=ClaimImportance.CRITICAL,
            citations=["А40-7777/2024"], verification_status=ClaimVerificationStatus.VERIFIED, issue_id="1",
        ),
        # An UNVERIFIED case-law claim (citation never resolved) must never
        # be assessed for relevance — there's nothing confirmed to assess.
        LegalClaim(
            claim="А00-0000/0000: fabricated", claim_type="case_law", importance=ClaimImportance.CRITICAL,
            citations=[], verification_status=ClaimVerificationStatus.UNVERIFIED, issue_id="1",
        ),
    ]

    relevance = await engine._assess_case_law_relevance(claims, issues, facts=["перечисление средств по договору займа"])  # noqa: SLF001

    assert len(relevance) == 1
    # Deterministic fields come straight from the DB row and are always
    # correct regardless of whether the LLM narrative assessment succeeds.
    assert relevance[0].case_number == "А40-7777/2024"
    assert relevance[0].court_level_label == "Верховный Суд РФ"
    assert relevance[0].decision_date == "2019-06-01"
    assert relevance[0].outcome == "granted"
    # MockLLMProvider's schema-conformant-empty response can't satisfy a
    # strict enum (empty string isn't a valid "stance") — this must degrade
    # to an honest "unassessed" narrative, never crash or fabricate a stance.
    assert relevance[0].assessed is False
    assert relevance[0].stance == "unassessed"


@pytest.mark.asyncio
async def test_relevance_deduplicates_repeated_case_numbers(db_session):
    await _seed_verified_decision(db_session, "А40-8888/2024")

    engine = LegalResearchEngine(db_session, LLMGateway(provider=MockLLMProvider()))
    issues = [LegalIssue(id="1", title="issue", description="d", priority=1)]
    claims = [
        LegalClaim(
            claim="c1", claim_type="case_law", importance=ClaimImportance.CRITICAL,
            citations=["А40-8888/2024"], verification_status=ClaimVerificationStatus.VERIFIED, issue_id="1",
        ),
        LegalClaim(
            claim="c2 (same decision retrieved twice)", claim_type="case_law", importance=ClaimImportance.IMPORTANT,
            citations=["А40-8888/2024"], verification_status=ClaimVerificationStatus.VERIFIED, issue_id="1",
        ),
    ]

    relevance = await engine._assess_case_law_relevance(claims, issues, facts=[])  # noqa: SLF001
    assert len(relevance) == 1


@pytest.mark.asyncio
async def test_relevance_surfaces_a_weakly_similar_case_honestly_rather_than_dropping_it(db_session):
    """P2 §12 — a weakly-similar decision must still be reported, with its
    low similarity visible, never silently omitted or inflated.
    """
    await _seed_verified_decision(db_session, "А40-1111/2020")
    decision = (
        await db_session.execute(select(CourtDecision).where(CourtDecision.case_number == "А40-1111/2020"))
    ).scalars().first()

    provider = _FixedRelevanceProvider(
        {
            "factual_similarity": "low", "legal_issue_similarity": "low",
            "procedural_posture_note": "Иной предмет спора — аренда, а не заём.",
            "stance": "distinguishable", "distinguishing_facts": ["Спор об аренде, а не о займе"],
            "remains_useful": False,
        }
    )

    relevance = await assess_case_law_relevance(
        LLMGateway(provider=provider), decision=decision, authority=AuthorityLevel.SUPREME_COURT,
        issue_title="Заключение договора конклюдентными действиями", case_facts=["перечисление средств"],
    )

    assert relevance.assessed is True
    assert relevance.factual_similarity == "low"
    assert relevance.legal_issue_similarity == "low"
    assert relevance.stance == "distinguishable"
    assert relevance.remains_useful is False
    assert relevance.distinguishing_facts == ["Спор об аренде, а не о займе"]


@pytest.mark.asyncio
async def test_relevance_surfaces_authority_that_supports_the_opponent_distinctly(db_session):
    """P2 §10/§12 — a verified decision that cuts AGAINST the theory being
    examined must be labeled 'against', never folded into supporting
    authority just because it's real and on-topic.
    """
    await _seed_verified_decision(db_session, "А40-2222/2021")
    decision = (
        await db_session.execute(select(CourtDecision).where(CourtDecision.case_number == "А40-2222/2021"))
    ).scalars().first()

    provider = _FixedRelevanceProvider(
        {
            "factual_similarity": "high", "legal_issue_similarity": "high",
            "procedural_posture_note": "Суд отказал в аналогичном требовании о признании договора заключенным.",
            "stance": "against", "distinguishing_facts": [], "remains_useful": True,
        }
    )

    relevance = await assess_case_law_relevance(
        LLMGateway(provider=provider), decision=decision, authority=AuthorityLevel.FIRST_INSTANCE,
        issue_title="Заключение договора конклюдентными действиями", case_facts=["перечисление средств"],
    )

    assert relevance.stance == "against"
    assert relevance.factual_similarity == "high"
    assert relevance.remains_useful is True
