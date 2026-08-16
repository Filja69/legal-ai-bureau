"""ContractIntelligenceEngine — orchestrates the full Phase 4 pipeline
(brief's DOCUMENT -> ... -> FINAL CONTRACT REPORT diagram), persisting every
stage so re-running against the same version is idempotent (brief §48) and
the trace is auditable. Reuses Phase 2/3 infrastructure unchanged:
LegalResearchEngine for risk verification, LLMGateway for the (currently
mock) classification hook, CitationValidator transitively through research.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import ContractAuditActions, write_audit_event
from app.domains.contracts.alternative_clause import propose_alternative
from app.domains.contracts.obligations import extract_obligations
from app.domains.contracts.recommendations import recommend
from app.domains.contracts.redline import diff_ops_to_dicts, word_diff
from app.domains.contracts.report import build_report
from app.domains.contracts.risk_detection import run_all_detectors
from app.domains.contracts.risk_verification import VerifiedRisk
from app.domains.contracts.severity import compute_score, score_to_severity
from app.domains.contracts.structure_extractor import ContractStructureExtractor
from app.domains.contracts.summary import build_summary
from app.domains.contracts.two_lawyer_review import ReviewedRisk, two_lawyer_review
from app.llm.routing.gateway import LLMGateway
from app.models.contracts import (
    AgreementStatus,
    AlternativeClause,
    AnalysisStatus,
    Contract,
    ContractClause,
    ContractObligation,
    ContractRecommendation,
    ContractReview,
    ContractReviewStatus,
    ContractRisk,
    ContractVersion,
    PartyPerspective,
    RecommendationAction,
    RedlineChange,
    ReviewDepth,
    RiskVerificationStatus,
)
from app.models.embedding_chunk import EmbeddingChunk


class ContractAnalysisFailedError(Exception):
    pass


def compute_configuration_hash(
    version_id: uuid.UUID, party_perspective: PartyPerspective, review_depth: ReviewDepth, jurisdiction: str,
    effective_at: date | None = None,
) -> str:
    raw = f"{version_id}:{party_perspective.value}:{review_depth.value}:{jurisdiction}:{effective_at.isoformat() if effective_at else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ContractIntelligenceEngine:
    def __init__(self, session: AsyncSession, llm_gateway: LLMGateway, organization_id: uuid.UUID, workspace_id: uuid.UUID,
        user_id: uuid.UUID | None = None) -> None:
        self._session = session
        self._llm = llm_gateway
        self._organization_id = organization_id
        self._workspace_id = workspace_id
        self._user_id = user_id

    async def analyze(
        self,
        contract: Contract,
        version: ContractVersion,
        party_perspective: PartyPerspective = PartyPerspective.NEUTRAL,
        review_depth: ReviewDepth = ReviewDepth.STANDARD,
        jurisdiction: str = "RU",
        effective_at: date | None = None,
        force: bool = False,
    ) -> ContractReview:
        config_hash = compute_configuration_hash(version.id, party_perspective, review_depth, jurisdiction, effective_at)

        if not force:
            existing = await self._find_existing_review(version.id, config_hash)
            if existing is not None:
                return existing

        await write_audit_event(
            self._session, organization_id=self._organization_id, workspace_id=self._workspace_id, user_id=self._user_id,
            action=ContractAuditActions.ANALYSIS_STARTED, target_type="contract", target_id=contract.id,
        )

        review = ContractReview(
            workspace_id=self._workspace_id, contract_id=contract.id, version_id=version.id,
            party_perspective=party_perspective, review_depth=review_depth,
            status=ContractReviewStatus.RUNNING, analysis_configuration_hash=config_hash,
        )
        self._session.add(review)
        await self._session.flush()

        try:
            t0 = time.perf_counter()
            extractor = ContractStructureExtractor()
            extracted_clauses = extractor.extract(version.content)

            clause_rows: list[ContractClause] = []
            for ec in extracted_clauses:
                row = ContractClause(
                    workspace_id=self._workspace_id, contract_id=contract.id, version_id=version.id,
                    clause_number=ec.clause_number, clause_type=ec.clause_type,
                    original_text=ec.original_text, normalized_text=ec.normalized_text,
                    position_start=ec.position_start, position_end=ec.position_end, confidence=ec.confidence,
                )
                self._session.add(row)
                clause_rows.append(row)
            await self._session.flush()

            obligations = extract_obligations(extracted_clauses)
            for ob in obligations:
                self._session.add(
                    ContractObligation(
                        workspace_id=self._workspace_id, contract_id=contract.id, clause_id=clause_rows[ob.clause_index].id,
                        party=ob.party, action=ob.action, deadline=ob.deadline, obligation_type=ob.obligation_type,
                    )
                )

            summary = build_summary(extracted_clauses, [o.action for o in obligations])
            clause_extraction_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            outcome = (
                await two_lawyer_review(self._session, self._llm, extracted_clauses, contract.contract_type, jurisdiction, effective_at)
                if review_depth != ReviewDepth.QUICK
                else None
            )
            if outcome is None:
                # QUICK mode: structural detection only, no Legal Research
                # roundtrip per risk — a deliberate speed/thoroughness tradeoff
                # (brief §31).
                candidates = run_all_detectors(extracted_clauses, contract.contract_type)
                reviewed_risks = [
                    ReviewedRisk(
                        verified_risk=VerifiedRisk(
                            candidate=c, verification_status=RiskVerificationStatus.UNVERIFIED, legal_basis=None,
                            citations=[], confidence="low", research_id=None, has_conflicting_practice=False,
                        ),
                        agreement_status=AgreementStatus.REQUIRES_HUMAN_REVIEW,
                        note="QUICK review depth — not independently re-verified.",
                    )
                    for c in candidates
                ]
            else:
                reviewed_risks = outcome.risks
            research_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            report = build_report(contract.contract_type, summary, reviewed_risks)
            review_ms = (time.perf_counter() - t0) * 1000

            redline_start = time.perf_counter()

            for reviewed in reviewed_risks:
                candidate = reviewed.verified_risk.candidate
                clause_id = clause_rows[candidate.clause_index].id if candidate.clause_index is not None else None
                severity = score_to_severity(compute_score(candidate.severity_inputs))

                risk_row = ContractRisk(
                    workspace_id=self._workspace_id, contract_id=contract.id, version_id=version.id, clause_id=clause_id,
                    risk_type=candidate.risk_type, severity=severity, category=candidate.category,
                    classification=candidate.classification, title=candidate.title, description=candidate.description,
                    why_it_matters=candidate.why_it_matters, legal_basis=reviewed.verified_risk.legal_basis,
                    party_perspective=party_perspective, confidence=reviewed.verified_risk.confidence,
                    verification_status=reviewed.verified_risk.verification_status,
                    research_id=reviewed.verified_risk.research_id, citations=reviewed.verified_risk.citations,
                    agreement_status=reviewed.agreement_status, detector=candidate.detector,
                )
                self._session.add(risk_row)
                await self._session.flush()

                await write_audit_event(
                    self._session, organization_id=self._organization_id, workspace_id=self._workspace_id, user_id=self._user_id,
                    action=ContractAuditActions.RISK_CREATED, target_type="contract_risk", target_id=risk_row.id,
                )

                rec = recommend(reviewed.verified_risk)
                rec_row = ContractRecommendation(
                    workspace_id=self._workspace_id, risk_id=risk_row.id, priority=rec.priority, action=rec.action,
                    reason=rec.reason, legal_basis=rec.legal_basis, commercial_reason=rec.commercial_reason,
                )
                self._session.add(rec_row)
                await write_audit_event(
                    self._session, organization_id=self._organization_id, workspace_id=self._workspace_id, user_id=self._user_id,
                    action=ContractAuditActions.RECOMMENDATION_CREATED, target_type="contract_recommendation", target_id=None,
                )

                if rec.action == RecommendationAction.REWRITE and clause_id is not None:
                    draft = propose_alternative(reviewed.verified_risk)
                    if draft is not None:
                        assert candidate.clause_index is not None  # guaranteed by clause_id is not None above
                        clause_row = clause_rows[candidate.clause_index]
                        alt_row = AlternativeClause(
                            workspace_id=self._workspace_id, original_clause_id=clause_id,
                            original_text=clause_row.original_text, proposed_text=draft.proposed_text,
                            change_reason=draft.change_reason, legal_basis=draft.legal_basis,
                            risk_reduction=draft.risk_reduction, commercial_tradeoff=None,
                        )
                        self._session.add(alt_row)
                        await self._session.flush()

                        ops = word_diff(clause_row.original_text, draft.proposed_text)
                        redline_row = RedlineChange(
                            workspace_id=self._workspace_id, contract_id=contract.id, clause_id=clause_id,
                            risk_id=risk_row.id, alternative_clause_id=alt_row.id,
                            research_id=reviewed.verified_risk.research_id, reason=draft.change_reason,
                            diff_ops=diff_ops_to_dicts(ops),
                        )
                        self._session.add(redline_row)
                        await write_audit_event(
                            self._session, organization_id=self._organization_id, workspace_id=self._workspace_id, user_id=self._user_id,
                            action=ContractAuditActions.REDLINE_CREATED, target_type="redline_change", target_id=None,
                        )

            redline_ms = (time.perf_counter() - redline_start) * 1000
            total_ms = clause_extraction_ms + research_ms + review_ms + redline_ms

            review.status = ContractReviewStatus.COMPLETED
            review.executive_summary = report.executive_summary
            review.risk_summary = report.risk_summary
            review.overall_score = report.overall_score
            review.knowledge_snapshot = await self._knowledge_snapshot()
            review.performance_ms = {
                "clause_extraction_ms": round(clause_extraction_ms, 2),
                "risk_detection_and_research_ms": round(research_ms, 2),
                "review_ms": round(review_ms, 2),
                "redline_ms": round(redline_ms, 2),
                "total_ms": round(total_ms, 2),
            }

            await write_audit_event(
                self._session, organization_id=self._organization_id, workspace_id=self._workspace_id, user_id=self._user_id,
                action=ContractAuditActions.ANALYSIS_COMPLETED, target_type="contract", target_id=contract.id,
                result_summary=f"score={report.overall_score} risks={len(reviewed_risks)}",
            )

        except Exception as exc:  # noqa: BLE001 — must record ANALYSIS_FAILED, never leave a silent partial row
            review.status = ContractReviewStatus.FAILED
            await write_audit_event(
                self._session, organization_id=self._organization_id, workspace_id=self._workspace_id, user_id=self._user_id,
                action=ContractAuditActions.ANALYSIS_FAILED, target_type="contract", target_id=contract.id,
                result_summary=str(exc),
            )
            await self._session.flush()
            raise ContractAnalysisFailedError(str(exc)) from exc

        await self._session.flush()
        return review

    async def _find_existing_review(self, version_id: uuid.UUID, config_hash: str) -> ContractReview | None:
        result = await self._session.execute(
            select(ContractReview).where(
                ContractReview.version_id == version_id,
                ContractReview.analysis_configuration_hash == config_hash,
                ContractReview.status == ContractReviewStatus.COMPLETED,
            )
        )
        existing = result.scalars().first()
        if existing is None:
            return None

        current_snapshot = await self._knowledge_snapshot()
        if existing.knowledge_snapshot.get("total_chunks") != current_snapshot["total_chunks"]:
            existing.analysis_status = AnalysisStatus.STALE
            await self._session.flush()
        return existing

    async def _knowledge_snapshot(self) -> dict:
        total = await self._session.execute(select(func.count()).select_from(EmbeddingChunk))
        mock = await self._session.execute(select(func.count()).select_from(EmbeddingChunk).where(EmbeddingChunk.is_mock.is_(True)))
        return {"total_chunks": total.scalar_one(), "mock_chunks": mock.scalar_one()}
