"""LegalResearchEngine — brief's full pipeline (§2, §16-36), orchestrating
every module in this package. This is the "research planning -> retrieval ->
evidence validation -> reasoning -> independent verification -> answer"
sequence the brief demands instead of `question -> LLM -> answer`.

Nothing here talks to Anthropic/OpenAI directly — every LLM touchpoint goes
through the injected LLMGateway (LEGAL-ARCHITECTURE.md §4), and every
citation is independently re-verified through CitationValidator (Phase 2)
rather than trusted from retrieval or from the reasoner's own claims.
"""
from __future__ import annotations

import time

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.legal_research.confidence import compute_citation_coverage, compute_confidence, inputs_from_pipeline
from app.domains.legal_research.conflict_detection import LegalConflictDetector
from app.domains.legal_research.counterargument import CounterArgumentAgent
from app.domains.legal_research.evidence_ranking import EvidenceRanker
from app.domains.legal_research.fact_extraction import FactExtractor
from app.domains.legal_research.issue_identification import IssueIdentifier, ResearchPlanner
from app.domains.legal_research.models import (
    ClaimVerificationStatus,
    ConfidenceLevel,
    KnowledgeSnapshot,
    LegalResearchRequest,
    LegalResearchResult,
    ResearchMode,
    ResearchTrace,
)
from app.domains.legal_research.query_generation import LegalQueryGenerator
from app.domains.legal_research.reasoning import LegalReasoner
from app.domains.legal_research.retrieval_pipeline import MultiStageRetriever
from app.domains.legal_research.review import review
from app.domains.legal_research.temporal_consistency import TemporalConsistencyChecker, classify_issue_type
from app.llm.routing.gateway import LLMGateway
from app.models.embedding_chunk import EmbeddingChunk

logger = structlog.get_logger(__name__)


class LegalResearchEngine:
    def __init__(self, session: AsyncSession, llm_gateway: LLMGateway) -> None:
        self._session = session
        self._llm = llm_gateway
        self._fact_extractor = FactExtractor(llm_gateway)
        self._issue_identifier = IssueIdentifier(llm_gateway)
        self._planner = ResearchPlanner()
        self._query_generator = LegalQueryGenerator(llm_gateway)
        self._retriever = MultiStageRetriever(session)
        self._ranker = EvidenceRanker(session)
        self._reasoner = LegalReasoner(session, llm_gateway)
        self._counterarguer = CounterArgumentAgent(session, llm_gateway)
        self._conflict_detector = LegalConflictDetector(session)
        self._temporal_checker = TemporalConsistencyChecker()
        self._llm_calls = 0

    async def run(self, request: LegalResearchRequest) -> tuple[LegalResearchResult, ResearchTrace]:
        perf: dict[str, float] = {}
        trace = ResearchTrace(question=request.question)
        effective_at_iso = request.effective_at.isoformat() if request.effective_at else None

        try:
            t0 = time.perf_counter()
            facts, missing_facts = await self._fact_extractor.extract(request.question, request.facts)
            self._llm_calls += 1
            perf["fact_extraction_ms"] = _ms(t0)

            t0 = time.perf_counter()
            issues = await self._issue_identifier.identify(request.question, request.facts)
            self._llm_calls += 1
            for issue in issues:
                issue.issue_type = classify_issue_type(issue.title, issue.description)
            plan = self._planner.build_plan(issues, request.jurisdiction, request.effective_at)
            perf["planning_ms"] = _ms(t0)

            t0 = time.perf_counter()
            all_queries = []
            for issue in plan.issues:
                issue_queries = await self._query_generator.generate(issue)
                self._llm_calls += 1
                all_queries.extend(issue_queries)
            trace.queries = [q.text for q in all_queries]

            pool = await self._retriever.run(all_queries, request.jurisdiction, effective_at_iso, request.facts)
            trace.retrieved_count = len(pool.items)
            pool = await self._ranker.rank(pool)
            trace.filtered_count = len(pool.items)
            perf["retrieval_ms"] = _ms(t0)

            t0 = time.perf_counter()
            all_claims = []
            analysis: list[str] = []
            executive_conclusion = ""
            for issue in plan.issues:
                issue_evidence = [e for e in pool.items if e.issue_id in (issue.id, None)]
                claims, narrative = await self._reasoner.reason(
                    issue, issue_evidence, request.facts, request.effective_at
                )
                self._llm_calls += 1
                all_claims.extend(claims)
                analysis.append(f"{issue.title}: {narrative}")
                if issue.priority == 1:
                    conclusion_claim = next((c for c in claims if c.claim_type == "conclusion"), None)
                    if conclusion_claim:
                        executive_conclusion = conclusion_claim.claim
            perf["reasoning_ms"] = _ms(t0)

            t0 = time.perf_counter()
            # QUICK_ANSWER (brief §39) intentionally skips the adversarial
            # counterargument pass and conflict detection for latency — it
            # trades thoroughness for speed, not correctness of what it does return.
            counter_evidence = []
            counterarguments: list[str] = []
            conflicts = []
            if request.requested_output != ResearchMode.QUICK_ANSWER:
                primary_issue = next((i for i in plan.issues if i.priority == 1), plan.issues[0])
                counter_evidence = await self._counterarguer.find(
                    primary_issue, executive_conclusion, request.jurisdiction, effective_at_iso
                )
                self._llm_calls += 1
                counterarguments = [f"{e.citation}: {e.text}" for e in counter_evidence]
                conflicts = await self._conflict_detector.detect(pool.items + counter_evidence)
            trace.counterarguments_found = len(counterarguments)
            trace.conflicts_found = len(conflicts)

            temporal_warnings = self._temporal_checker.check(pool.items, request.effective_at)
            perf["counterargument_and_conflict_ms"] = _ms(t0)

            t0 = time.perf_counter()
            findings = review(plan.issues, all_claims, missing_facts, conflicts, temporal_warnings)
            trace.review_notes = findings.notes
            citation_coverage = compute_citation_coverage(all_claims)
            confidence = compute_confidence(
                inputs_from_pipeline(citation_coverage, pool.items, findings, temporal_warnings)
            )
            perf["review_and_confidence_ms"] = _ms(t0)
        except Exception as exc:  # noqa: BLE001 — a hard failure must produce RESEARCH_FAILED, never a fabricated answer
            logger.error("research_failed", question=request.question, error=str(exc))
            trace.performance_ms = perf
            trace.llm_calls = self._llm_calls
            failed_result = LegalResearchResult(
                executive_conclusion="", confidence=ConfidenceLevel.LOW,
                status="research_failed", escalate_to_human=True, escalation_reasons=[f"Research pipeline failed: {exc}"],
            )
            return failed_result, trace

        status = "blocked_unverified_claim" if any(
            c.claim_type == "conclusion" and c.verification_status == ClaimVerificationStatus.UNSUPPORTED_CRITICAL
            for c in all_claims
        ) else "completed"

        escalation_reasons = _escalation_reasons(findings, confidence)

        citations = sorted({cit for c in all_claims for cit in c.citations})

        result = LegalResearchResult(
            executive_conclusion=executive_conclusion or "Недостаточно подтвержденных данных для формирования вывода.",
            confidence=confidence,
            issues=plan.issues,
            facts=facts,
            claims=all_claims,
            analysis=analysis,
            counterarguments=counterarguments,
            conflicts=conflicts,
            risks=[note for note in findings.notes],
            missing_facts=missing_facts,
            recommended_actions=_recommended_actions(missing_facts, escalation_reasons),
            citations=citations,
            citation_coverage=citation_coverage,
            escalate_to_human=bool(escalation_reasons),
            escalation_reasons=escalation_reasons,
            status=status,
        )

        trace.facts_count = len(facts)
        trace.issues = [i.title for i in plan.issues]
        trace.performance_ms = perf
        trace.performance_ms["total_ms"] = sum(perf.values())
        trace.llm_calls = self._llm_calls
        trace.knowledge_snapshot = await self._knowledge_snapshot()

        return result, trace

    async def _knowledge_snapshot(self) -> KnowledgeSnapshot:
        total = await self._session.execute(select(func.count()).select_from(EmbeddingChunk))
        mock = await self._session.execute(select(func.count()).select_from(EmbeddingChunk).where(EmbeddingChunk.is_mock.is_(True)))
        return KnowledgeSnapshot(total_chunks=total.scalar_one(), mock_chunks=mock.scalar_one())


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _escalation_reasons(findings, confidence: ConfidenceLevel) -> list[str]:
    reasons = []
    if findings.unsupported_critical_claims:
        reasons.append("Critical legal claim lacks a verified citation.")
    if not findings.all_critical_facts_addressed:
        reasons.append("Critical facts are missing.")
    if findings.has_conflicting_practice and confidence != ConfidenceLevel.HIGH:
        reasons.append("Court practice is not uniform and confidence is not high.")
    return reasons


def _recommended_actions(missing_facts, escalation_reasons: list[str]) -> list[str]:
    actions = [m.question for m in missing_facts if m.criticality.value == "critical"]
    if escalation_reasons:
        actions.append("Рекомендуется проверка результата квалифицированным юристом.")
    return actions
