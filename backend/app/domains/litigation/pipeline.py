"""LitigationCaseEngine — Phase 9.3 orchestration. The only place that reads
Document/DocumentChunk rows, writes CaseFact/CaseFactEvidence/CaseEvent/
CaseContradiction rows, and decides idempotency (brief §34: repeated
extraction must not create uncontrolled duplicates) — every domain module
this calls (`fact_extractor`, `fact_dedup`, `timeline_builder`,
`contradiction_detector`, `evidence_matrix`) stays a pure function with no
DB access, same separation as `app/domains/documents/pipeline.py`.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.litigation.allegation_extractor import ALLEGATION_ELIGIBLE_ROLES, extract_allegation_candidates
from app.domains.litigation.case_relationships import (
    CaseHypothesisInput,
    CasePartyRelationshipInput,
    PartyRelationshipFinding,
    build_party_relationship_findings,
)
from app.domains.litigation.case_result_summary import CaseResultSummary, build_case_result_summary
from app.domains.litigation.conduct_patterns import detect_payment_pattern
from app.domains.litigation.contract_forensics import build_contract_version_matrix
from app.domains.litigation.contradiction_detector import (
    AllegationInput,
    ClaimEvidenceContradiction,
    ContradictionCandidate,
    PaymentOrderInput,
    detect_claim_theory_tensions,
    detect_claim_vs_evidence_contradictions,
    detect_contradictions,
)
from app.domains.litigation.course_of_dealing import detect_course_of_dealing
from app.domains.litigation.evidence_matrix import EvidenceMatrixRow, build_evidence_matrix
from app.domains.litigation.fact_dedup import CanonicalFact, deduplicate_facts
from app.domains.litigation.fact_extractor import FactEvidenceCandidate, extract_fact_candidates
from app.domains.litigation.interest_damages import extract_interest_calculation_table, extract_interest_claim
from app.domains.litigation.master_report import (
    MasterCaseReport,
    RelatedLitigationInput,
    build_burden_map,
    build_case_map,
    build_claim_contradiction_findings,
    build_contract_formation_findings,
    build_contract_mismatch_finding,
    build_corporate_relationship_findings,
    build_course_of_dealing_finding,
    build_court_scenarios,
    build_credibility_synthesis_finding,
    build_draft_response_structure,
    build_evidence_gap_findings,
    build_interest_damages_finding,
    build_interest_table_finding,
    build_notice_timeline_finding,
    build_one_pager,
    build_opposing_party_questions,
    build_payment_pattern_finding,
    build_related_litigation_findings,
    build_temporal_issue_findings,
    build_theory_vs_conduct_finding,
    build_timing_synthesis_finding,
    rank_findings,
)
from app.domains.litigation.notice_timeline import extract_notice_timeline
from app.domains.litigation.payment_extractor import extract_payment_order_candidate
from app.domains.litigation.temporal_reasoning import analyze_temporal_issues, extract_document_own_date
from app.domains.litigation.timeline_builder import build_timeline
from app.domains.litigation.transaction_identity import EvidenceSource, build_canonical_transactions
from app.models.legal_knowledge import LawVersion
from app.models.matters import (
    Case,
    CaseAllegation,
    CaseContradiction,
    CaseDocument,
    CaseDocumentRole,
    CaseEvent,
    CaseFact,
    CaseFactEvidence,
    CaseHypothesis,
    CaseParty,
    CasePartyRelationship,
    CasePaymentOrder,
    CaseRelatedLitigation,
    DateType,
    Document,
    DocumentChunk,
    DocumentStatus,
    FactStatus,
    FactType,
    PaymentExecutionStatus,
    RelationshipType,
)

logger = structlog.get_logger(__name__)


@dataclass
class MoneyFlowTransaction:
    """One CANONICAL underlying transaction — see transaction_identity.py.
    `payment_order_id`/`document_id` remain the representative (most-
    complete) row's identifiers for backward compatibility; every row that
    corroborates this same transaction (a bank statement, a register entry,
    etc.) is preserved in `evidence_sources`, never discarded.
    """

    payment_order_id: uuid.UUID
    document_id: uuid.UUID
    payment_date: date | None
    amount: str | None
    payer: str | None
    recipient: str | None
    referenced_contract_date: date | None
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str | None = None


@dataclass
class MoneyFlowSummary:
    transaction_count: int
    transactions: list[MoneyFlowTransaction]
    total_amount: str
    referenced_contract_dates: dict[str, int]  # ISO date -> count of payments citing it
    referenced_contract_numbers: dict[str, int]  # raw number string -> count (excludes payments with no number stated)


class LitigationCaseEngine:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def extract_facts(self, case: Case) -> list[CaseFact]:
        """Idempotent: delete-then-insert (brief §34) — case_contradictions
        cascades via its FK ondelete="CASCADE" on fact_a_id/fact_b_id, so a
        re-extraction never leaves a contradiction pointing at a fact that
        no longer exists.
        """
        case_documents = (await self._session.execute(select(CaseDocument).where(CaseDocument.case_id == case.id))).scalars().all()

        candidates = []
        skipped_not_ready = 0
        for case_document in case_documents:
            document = await self._session.get(Document, case_document.document_id)
            if document is None or document.status != DocumentStatus.READY:
                skipped_not_ready += 1
                continue
            chunks = (await self._session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id))).scalars().all()
            for chunk in chunks:
                candidates.extend(extract_fact_candidates(document, chunk))

        canonical = deduplicate_facts(candidates)

        await self._session.execute(delete(CaseFact).where(CaseFact.case_id == case.id))
        await self._session.flush()

        persisted: list[CaseFact] = []
        for cf in canonical:
            fact = CaseFact(
                workspace_id=case.workspace_id,
                case_id=case.id,
                statement=cf.statement,
                fact_type=cf.fact_type,
                status=FactStatus.SUPPORTED,  # brief §7: only ever assigned when real evidence backs it, which is guaranteed here
                normalized_value=cf.normalized_value,
            )
            self._session.add(fact)
            await self._session.flush()
            for evidence in cf.evidence:
                self._session.add(
                    CaseFactEvidence(
                        workspace_id=case.workspace_id,
                        case_fact_id=fact.id,
                        document_id=evidence.document_id,
                        chunk_id=evidence.chunk_id,
                        page_number=evidence.page_number,
                        section_path=evidence.section_path,
                        excerpt=evidence.excerpt,
                    )
                )
            persisted.append(fact)
        await self._session.flush()

        logger.info(
            "case_facts_extracted",
            case_id=str(case.id),
            workspace_id=str(case.workspace_id),
            fact_count=len(persisted),
            documents_skipped_not_ready=skipped_not_ready,
        )
        return persisted

    async def _ready_case_documents(self, case_id: uuid.UUID, roles: set[CaseDocumentRole]) -> list[tuple[Document, list[DocumentChunk]]]:
        case_documents = (
            await self._session.execute(
                select(CaseDocument).where(CaseDocument.case_id == case_id, CaseDocument.role.in_(roles))
            )
        ).scalars().all()

        out: list[tuple[Document, list[DocumentChunk]]] = []
        for case_document in case_documents:
            document = await self._session.get(Document, case_document.document_id)
            if document is None or document.status != DocumentStatus.READY:
                continue
            chunks = (
                await self._session.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
            ).scalars().all()
            out.append((document, list(chunks)))
        return out

    async def extract_allegations(self, case: Case) -> list[CaseAllegation]:
        """E1 — idempotent delete-then-insert, same pattern as extract_facts.
        Only scans CLAIM/RESPONSE/COURT_FILING-role documents (see
        allegation_extractor.ALLEGATION_ELIGIBLE_ROLES) — an allegation is an
        assertion made BY a party in a pleading, not something to look for in
        a payment order or a contract.
        """
        eligible_roles = {CaseDocumentRole(r) for r in ALLEGATION_ELIGIBLE_ROLES}
        documents_with_chunks = await self._ready_case_documents(case.id, eligible_roles)

        candidates = []
        for document, chunks in documents_with_chunks:
            for chunk in chunks:
                candidates.extend(extract_allegation_candidates(document, chunk))

        await self._session.execute(delete(CaseAllegation).where(CaseAllegation.case_id == case.id))
        await self._session.flush()

        persisted: list[CaseAllegation] = []
        for candidate in candidates:
            allegation = CaseAllegation(
                workspace_id=case.workspace_id,
                case_id=case.id,
                document_id=candidate.document_id,
                chunk_id=candidate.chunk_id,
                page_number=candidate.page_number,
                statement_text=candidate.statement_text,
                excerpt=candidate.excerpt,
                allegation_type=candidate.allegation_type,
            )
            self._session.add(allegation)
            persisted.append(allegation)
        await self._session.flush()

        logger.info("case_allegations_extracted", case_id=str(case.id), workspace_id=str(case.workspace_id), count=len(persisted))
        return persisted

    async def extract_payment_orders(self, case: Case) -> list[CasePaymentOrder]:
        """E3 — idempotent delete-then-insert. Only scans PAYMENT_DOCUMENT-
        role documents. One candidate per (document, chunk) pair that
        matched anything at all — see payment_extractor.py.
        """
        documents_with_chunks = await self._ready_case_documents(case.id, {CaseDocumentRole.PAYMENT_DOCUMENT})

        candidates = []
        for document, chunks in documents_with_chunks:
            for chunk in chunks:
                candidate = extract_payment_order_candidate(document, chunk)
                if candidate is not None:
                    candidates.append(candidate)

        await self._session.execute(delete(CasePaymentOrder).where(CasePaymentOrder.case_id == case.id))
        await self._session.flush()

        persisted: list[CasePaymentOrder] = []
        for candidate in candidates:
            payment_order = CasePaymentOrder(
                workspace_id=case.workspace_id,
                case_id=case.id,
                document_id=candidate.document_id,
                chunk_id=candidate.chunk_id,
                page_number=candidate.page_number,
                payment_date=candidate.payment_date,
                amount=candidate.amount,
                payer=candidate.payer,
                recipient=candidate.recipient,
                payment_purpose=candidate.payment_purpose,
                referenced_contract_type=candidate.referenced_contract_type,
                referenced_contract_date=candidate.referenced_contract_date,
                referenced_contract_number=candidate.referenced_contract_number,
                execution_status=PaymentExecutionStatus(candidate.execution_status),
                excerpt=candidate.excerpt,
            )
            self._session.add(payment_order)
            persisted.append(payment_order)
        await self._session.flush()

        logger.info("case_payment_orders_extracted", case_id=str(case.id), workspace_id=str(case.workspace_id), count=len(persisted))
        return persisted

    async def get_claim_evidence_contradictions(self, case: Case) -> list[ClaimEvidenceContradiction]:
        """E2 — computed at read time from already-persisted CaseAllegation/
        CasePaymentOrder rows (run extract_allegations/extract_payment_orders
        — or analyze() — first). Never persisted itself; see
        ContradictionType.CLAIM_VS_EVIDENCE's docstring for why.
        """
        allegations = (await self._session.execute(select(CaseAllegation).where(CaseAllegation.case_id == case.id))).scalars().all()
        payment_orders = (
            await self._session.execute(select(CasePaymentOrder).where(CasePaymentOrder.case_id == case.id))
        ).scalars().all()

        allegation_inputs = [
            AllegationInput(
                id=a.id, document_id=a.document_id, page_number=a.page_number, excerpt=a.excerpt,
                allegation_type=a.allegation_type,
            )
            for a in allegations
        ]
        payment_inputs = [
            PaymentOrderInput(
                id=p.id, document_id=p.document_id, page_number=p.page_number, excerpt=p.excerpt,
                referenced_contract_type=p.referenced_contract_type, referenced_contract_date=p.referenced_contract_date,
            )
            for p in payment_orders
        ]
        return detect_claim_vs_evidence_contradictions(allegation_inputs, payment_inputs)

    async def get_money_flow(self, case: Case) -> MoneyFlowSummary:
        """Computed at read time from CasePaymentOrder rows, assembled into
        CANONICAL transactions (transaction_identity.py) — a total and a
        grouping of referenced contract dates/numbers ONLY as a count of how
        many payments cite each one. Deliberately does not merge same-dated
        payments into "one obligation" — see payment_extractor.py's module
        docstring on why that's a candidate-linkage question, not a fact.

        More than one document (a payment order, a corroborating bank
        statement, a register entry) can describe the exact same real
        transfer — every one is preserved as evidence on its canonical
        transaction, never discarded; see transaction_identity.py for the
        multi-signal matching rule and its explicit refusal to merge on
        amount alone or amount+referenced_contract_date alone.
        """
        payment_orders_raw = (
            await self._session.execute(
                select(CasePaymentOrder).where(CasePaymentOrder.case_id == case.id).order_by(CasePaymentOrder.payment_date)
            )
        ).scalars().all()

        document_ids = {p.document_id for p in payment_orders_raw}
        document_titles: dict[uuid.UUID, str] = {}
        for document_id in document_ids:
            document = await self._session.get(Document, document_id)
            if document is not None:
                document_titles[document_id] = document.title

        canonical = sorted(
            build_canonical_transactions(list(payment_orders_raw), document_titles),
            key=lambda c: (c.transaction_date is None, c.transaction_date or date.min),
        )

        transactions = [
            MoneyFlowTransaction(
                payment_order_id=uuid.UUID(c.id), document_id=c.representative_document_id,
                payment_date=c.transaction_date, amount=c.amount, payer=c.payer, recipient=c.recipient,
                referenced_contract_date=c.referenced_contract_date,
                evidence_sources=[
                    EvidenceSource(
                        payment_order_id=e.payment_order_id, document_id=e.document_id, document_title=e.document_title,
                        page_number=e.page_number, excerpt=e.excerpt, evidence_type=e.evidence_type,
                    )
                    for e in c.evidence_sources
                ],
                matched_signals=c.matched_signals, needs_review=c.needs_review, review_reason=c.review_reason,
            )
            for c in canonical
        ]

        total = sum((float(c.amount) for c in canonical if c.amount is not None), 0.0)

        dates: dict[str, int] = {}
        numbers: dict[str, int] = {}
        for c in canonical:
            if c.referenced_contract_date is not None:
                key = c.referenced_contract_date.isoformat()
                dates[key] = dates.get(key, 0) + 1
            if c.referenced_contract_number is not None:
                numbers[c.referenced_contract_number] = numbers.get(c.referenced_contract_number, 0) + 1

        return MoneyFlowSummary(
            transaction_count=len(transactions), transactions=transactions, total_amount=f"{total:.2f}",
            referenced_contract_dates=dates, referenced_contract_numbers=numbers,
        )

    async def _load_canonical_facts(self, case_id: uuid.UUID, fact_type: FactType | None = None) -> list[tuple[uuid.UUID, CanonicalFact]]:
        stmt = select(CaseFact).where(CaseFact.case_id == case_id)
        if fact_type is not None:
            stmt = stmt.where(CaseFact.fact_type == fact_type)
        facts = (await self._session.execute(stmt)).scalars().all()
        if not facts:
            return []

        fact_ids = [f.id for f in facts]
        evidence_result = await self._session.execute(
            select(CaseFactEvidence).where(CaseFactEvidence.case_fact_id.in_(fact_ids))
        )
        evidence_rows = evidence_result.scalars().all()
        evidence_by_fact: dict[uuid.UUID, list[FactEvidenceCandidate]] = defaultdict(list)
        for row in evidence_rows:
            evidence_by_fact[row.case_fact_id].append(
                FactEvidenceCandidate(
                    document_id=row.document_id,
                    document_title="",  # not needed by timeline/contradiction logic, avoids an extra join
                    chunk_id=row.chunk_id,
                    page_number=row.page_number,
                    section_path=row.section_path,
                    excerpt=row.excerpt,
                )
            )

        return [
            (
                f.id,
                CanonicalFact(
                    fact_type=f.fact_type, statement=f.statement, normalized_value=f.normalized_value or "",
                    evidence=evidence_by_fact.get(f.id, []),
                ),
            )
            for f in facts
        ]

    async def build_timeline(self, case: Case) -> list[CaseEvent]:
        id_and_facts = await self._load_canonical_facts(case.id, fact_type=FactType.DATE)
        value_to_id = {cf.normalized_value: fact_id for fact_id, cf in id_and_facts}
        drafts = build_timeline([cf for _, cf in id_and_facts])

        await self._session.execute(delete(CaseEvent).where(CaseEvent.case_id == case.id))
        await self._session.flush()

        events: list[CaseEvent] = []
        for draft in drafts:
            event = CaseEvent(
                workspace_id=case.workspace_id,
                case_id=case.id,
                event_date=draft.event_date,
                date_type=draft.date_type,
                description=draft.description,
                event_type=draft.event_type,
                source_fact_id=value_to_id.get(draft.source_fact.normalized_value),
            )
            self._session.add(event)
            events.append(event)
        await self._session.flush()
        return events

    async def detect_and_persist_contradictions(self, case: Case) -> list[CaseContradiction]:
        id_and_facts = await self._load_canonical_facts(case.id)
        value_to_id = {(cf.fact_type, cf.normalized_value): fact_id for fact_id, cf in id_and_facts}
        candidates = detect_contradictions([cf for _, cf in id_and_facts])

        await self._session.execute(delete(CaseContradiction).where(CaseContradiction.case_id == case.id))
        await self._session.flush()

        persisted: list[CaseContradiction] = []
        for candidate in candidates:
            row = CaseContradiction(
                workspace_id=case.workspace_id,
                case_id=case.id,
                contradiction_type=candidate.contradiction_type,
                fact_a_id=value_to_id[(candidate.fact_a.fact_type, candidate.fact_a.normalized_value)],
                fact_b_id=value_to_id[(candidate.fact_b.fact_type, candidate.fact_b.normalized_value)],
                description=candidate.description,
            )
            self._session.add(row)
            persisted.append(row)
        await self._session.flush()
        return persisted

    async def get_evidence_matrix(self, case: Case) -> list[EvidenceMatrixRow]:
        """Computed at read time (not persisted) — cheap, and avoids a
        second staleness-tracking concept on top of CaseFact/CaseContradiction.
        """
        id_and_facts = await self._load_canonical_facts(case.id)
        id_to_fact = dict(id_and_facts)
        contradiction_result = await self._session.execute(select(CaseContradiction).where(CaseContradiction.case_id == case.id))
        contradiction_rows = contradiction_result.scalars().all()

        candidates: list[ContradictionCandidate] = []
        for row in contradiction_rows:
            fact_a = id_to_fact.get(row.fact_a_id)
            fact_b = id_to_fact.get(row.fact_b_id)
            if fact_a is not None and fact_b is not None:
                candidates.append(ContradictionCandidate(row.contradiction_type, fact_a, fact_b, row.description))

        return build_evidence_matrix([cf for _, cf in id_and_facts], candidates)

    async def analyze(self, case: Case) -> None:
        """One-shot convenience (brief §33's `POST /cases/{id}/analyze`):
        extract -> detect contradictions -> build timeline, in that
        dependency order, all idempotent. Also runs E1/E3 allegation and
        payment-order extraction, so get_claim_evidence_contradictions()/
        get_money_flow() have something to read immediately afterward —
        both stay read-only computed views, not run here.
        """
        await self.extract_facts(case)
        await self.detect_and_persist_contradictions(case)
        await self.build_timeline(case)
        await self.extract_allegations(case)
        await self.extract_payment_orders(case)

    async def _contract_amount_candidates(self, case_id: uuid.UUID) -> list[str]:
        """AMOUNT facts whose evidence traces to a CONTRACT-role document —
        reuses the already-existing generic fact_extractor output (it runs
        against every ready document regardless of role) rather than adding
        a new contract-specific extractor. Only used by the client-facing
        summary's amount-mismatch conclusion.
        """
        contract_document_ids = {
            cd.document_id
            for cd in (
                await self._session.execute(
                    select(CaseDocument).where(CaseDocument.case_id == case_id, CaseDocument.role == CaseDocumentRole.CONTRACT)
                )
            ).scalars().all()
        }
        if not contract_document_ids:
            return []

        amount_facts = (
            await self._session.execute(select(CaseFact).where(CaseFact.case_id == case_id, CaseFact.fact_type == FactType.AMOUNT))
        ).scalars().all()
        if not amount_facts:
            return []
        fact_by_id = {f.id: f for f in amount_facts}

        evidence_rows = (
            await self._session.execute(
                select(CaseFactEvidence).where(
                    CaseFactEvidence.case_fact_id.in_(fact_by_id.keys()),
                    CaseFactEvidence.document_id.in_(contract_document_ids),
                )
            )
        ).scalars().all()

        values: set[str] = set()
        for e in evidence_rows:
            normalized_value = fact_by_id[e.case_fact_id].normalized_value
            if normalized_value:
                values.add(normalized_value)
        return sorted(values)

    async def get_result_summary(self, case: Case) -> CaseResultSummary:
        """The client-facing Case Result Summary — computed at read time from
        already-persisted E1-E4 data (run analyze()/extract_*() first, same
        contract as get_claim_evidence_contradictions()/get_money_flow()).
        Zero LLM calls; see case_result_summary.py's module docstring.
        """
        parties = (await self._session.execute(select(CaseParty).where(CaseParty.case_id == case.id))).scalars().all()

        case_documents = (await self._session.execute(select(CaseDocument).where(CaseDocument.case_id == case.id))).scalars().all()
        roles_present = {cd.role for cd in case_documents}
        document_ids = {cd.document_id for cd in case_documents}
        document_titles: dict[uuid.UUID, str] = {}
        document_texts: dict[uuid.UUID, str] = {}
        for document_id in document_ids:
            document = await self._session.get(Document, document_id)
            if document is not None:
                document_titles[document_id] = document.title
                document_texts[document_id] = document.extracted_text or ""

        contract_documents = [
            (cd.document_id, document_titles.get(cd.document_id, "(deleted)"), document_texts.get(cd.document_id, ""))
            for cd in case_documents
            if cd.role == CaseDocumentRole.CONTRACT
        ]

        events = (
            await self._session.execute(
                select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.event_date.is_(None), CaseEvent.event_date)
            )
        ).scalars().all()
        key_dates = [(e.event_date, e.description) for e in events[:5]]

        claim_evidence_contradictions = await self.get_claim_evidence_contradictions(case)
        money_flow = await self.get_money_flow(case)

        id_and_facts = await self._load_canonical_facts(case.id)
        id_to_fact = dict(id_and_facts)
        contradiction_rows = (
            await self._session.execute(select(CaseContradiction).where(CaseContradiction.case_id == case.id))
        ).scalars().all()
        case_contradictions: list[ContradictionCandidate] = []
        for row in contradiction_rows:
            fact_a = id_to_fact.get(row.fact_a_id)
            fact_b = id_to_fact.get(row.fact_b_id)
            if fact_a is not None and fact_b is not None:
                case_contradictions.append(ContradictionCandidate(row.contradiction_type, fact_a, fact_b, row.description))

        contract_amount_candidates = await self._contract_amount_candidates(case.id)

        kb_count = (await self._session.execute(select(func.count()).select_from(LawVersion))).scalar_one()

        party_relationship_findings = await self.get_party_relationship_findings(case)

        return build_case_result_summary(
            party_names=[p.name for p in parties],
            document_count=len(case_documents),
            roles_present=roles_present,
            key_dates=key_dates,
            document_titles=document_titles,
            claim_evidence_contradictions=claim_evidence_contradictions,
            case_contradictions=case_contradictions,
            money_flow=money_flow,
            contract_amount_candidates=contract_amount_candidates,
            contract_documents=contract_documents,
            kb_is_empty=kb_count == 0,
            party_relationship_findings=party_relationship_findings,
        )

    # --- Case Intelligence: party relationships (built on top of E1-E4,
    # never touching build_timeline()/detect_and_persist_contradictions()/
    # money-flow logic). CasePartyRelationship/CaseHypothesis/
    # CaseRelatedLitigation rows are written directly by the API layer
    # (they're counsel-provided data, not extracted from documents) — this
    # engine only computes the read-time timing analysis and syncs
    # relationship-derived CaseEvent rows. ---

    _RELATIONSHIP_EVENT_TYPE: dict[RelationshipType, str] = {
        RelationshipType.DIRECTOR: "director_change",
        RelationshipType.SHAREHOLDER: "shareholder_change",
        RelationshipType.MEMBER: "shareholder_change",
        RelationshipType.OTHER: "corporate_event",
    }

    async def sync_relationship_timeline_events(self, case: Case) -> list[CaseEvent]:
        """Idempotent delete-then-insert, scoped to source_relationship_id
        IS NOT NULL — never touches fact-derived events (source_fact_id),
        and build_timeline() never touches these. One event per
        relationship start_date, and one more if end_date is set.
        """
        relationships = (
            await self._session.execute(select(CasePartyRelationship).where(CasePartyRelationship.case_id == case.id))
        ).scalars().all()

        await self._session.execute(
            delete(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.source_relationship_id.isnot(None))
        )
        await self._session.flush()

        party_ids = {r.subject_party_id for r in relationships} | {r.related_party_id for r in relationships}
        party_names: dict[uuid.UUID, str] = {}
        for party_id in party_ids:
            party = await self._session.get(CaseParty, party_id)
            if party is not None:
                party_names[party_id] = party.name

        events: list[CaseEvent] = []
        for rel in relationships:
            subject_name = party_names.get(rel.subject_party_id, "(unknown)")
            related_name = party_names.get(rel.related_party_id, "(unknown)")
            event_type = self._RELATIONSHIP_EVENT_TYPE[rel.relationship_type]
            if rel.start_date is not None:
                event = CaseEvent(
                    workspace_id=case.workspace_id, case_id=case.id, event_date=rel.start_date, date_type=DateType.EXACT,
                    description=f"{subject_name} становится «{rel.relationship_type.value}» в «{related_name}»",
                    event_type=event_type, source_relationship_id=rel.id,
                )
                self._session.add(event)
                events.append(event)
            if rel.end_date is not None:
                event = CaseEvent(
                    workspace_id=case.workspace_id, case_id=case.id, event_date=rel.end_date, date_type=DateType.EXACT,
                    description=f"{subject_name} перестаёт быть «{rel.relationship_type.value}» в «{related_name}»",
                    event_type=event_type, source_relationship_id=rel.id,
                )
                self._session.add(event)
                events.append(event)
        await self._session.flush()
        return events

    async def get_party_relationship_findings(self, case: Case) -> list[PartyRelationshipFinding]:
        """Computed at read time — cross-references relationship timing
        against this case's own payment dates (Money Flow), never inferring
        knowledge from status alone; see case_relationships.py.
        """
        relationships = (
            await self._session.execute(select(CasePartyRelationship).where(CasePartyRelationship.case_id == case.id))
        ).scalars().all()
        if not relationships:
            return []

        party_ids = {r.subject_party_id for r in relationships} | {r.related_party_id for r in relationships}
        party_names: dict[uuid.UUID, str] = {}
        for party_id in party_ids:
            party = await self._session.get(CaseParty, party_id)
            if party is not None:
                party_names[party_id] = party.name

        document_ids = {r.source_document_id for r in relationships if r.source_document_id is not None}
        document_titles: dict[uuid.UUID, str] = {}
        for document_id in document_ids:
            document = await self._session.get(Document, document_id)
            if document is not None:
                document_titles[document_id] = document.title

        hypotheses_rows = (
            await self._session.execute(select(CaseHypothesis).where(CaseHypothesis.case_id == case.id))
        ).scalars().all()
        hypotheses = [
            CaseHypothesisInput(
                id=h.id, category=h.category, statement=h.statement,
                required_verification=list(h.required_verification or []), related_relationship_id=h.related_relationship_id,
            )
            for h in hypotheses_rows
        ]

        money_flow = await self.get_money_flow(case)
        reference_dates = [t.payment_date for t in money_flow.transactions if t.payment_date is not None]

        relationship_inputs = [
            CasePartyRelationshipInput(
                id=r.id, subject_party_id=r.subject_party_id, subject_name=party_names.get(r.subject_party_id, "(unknown)"),
                related_party_id=r.related_party_id, related_party_name=party_names.get(r.related_party_id, "(unknown)"),
                relationship_type=r.relationship_type, start_date=r.start_date, end_date=r.end_date,
                verification_status=r.verification_status, source_document_id=r.source_document_id, source_excerpt=r.source_excerpt,
            )
            for r in relationships
        ]

        return build_party_relationship_findings(relationship_inputs, reference_dates, hypotheses, document_titles)

    # --- Master Case Report (top-level synthesis over everything above) ---

    async def _determine_our_side_role(self, case: Case) -> str:
        """Matches Case.client_name against CaseParty rows to find which
        procedural role (plaintiff/defendant) the case's own client holds —
        "unclear" if no match, never guessed. Drives helps_side/hurts_side
        attribution in master_report.py.
        """
        if not case.client_name:
            return "unclear"
        parties = (await self._session.execute(select(CaseParty).where(CaseParty.case_id == case.id))).scalars().all()
        for party in parties:
            if party.name.strip().lower() == case.client_name.strip().lower():
                if party.procedural_role.value in ("plaintiff", "defendant"):
                    return party.procedural_role.value
                return "unclear"
        return "unclear"

    async def _claim_document_facts(self, case: Case) -> tuple[list[str], list[str]]:
        """AMOUNT/DATE CaseFact values whose evidence traces to a CLAIM-role
        document — reuses the existing generic fact_extractor output, same
        pattern as _contract_amount_candidates(), for the Case Map section.
        """
        claim_document_ids = {
            cd.document_id
            for cd in (
                await self._session.execute(
                    select(CaseDocument).where(CaseDocument.case_id == case.id, CaseDocument.role == CaseDocumentRole.CLAIM)
                )
            ).scalars().all()
        }
        if not claim_document_ids:
            return [], []

        facts = (await self._session.execute(select(CaseFact).where(CaseFact.case_id == case.id))).scalars().all()
        fact_by_id = {f.id: f for f in facts}
        if not fact_by_id:
            return [], []

        evidence_rows = (
            await self._session.execute(
                select(CaseFactEvidence).where(
                    CaseFactEvidence.case_fact_id.in_(fact_by_id.keys()), CaseFactEvidence.document_id.in_(claim_document_ids)
                )
            )
        ).scalars().all()

        amounts: set[str] = set()
        dates: set[str] = set()
        for e in evidence_rows:
            fact = fact_by_id[e.case_fact_id]
            if not fact.normalized_value:
                continue
            if fact.fact_type == FactType.AMOUNT:
                amounts.add(fact.normalized_value)
            elif fact.fact_type == FactType.DATE:
                dates.add(fact.normalized_value)
        return sorted(amounts), sorted(dates)

    async def _claim_document_texts(self, case: Case) -> list[tuple[uuid.UUID, str, str]]:
        """(document_id, title, extracted_text) for every CLAIM-role
        document — same fetch shape as the CONTRACT-role fetch inside
        get_master_report(), reused by interest_damages.py's claim-text
        extraction so it never has to duplicate a document lookup.
        """
        claim_case_documents = (
            await self._session.execute(
                select(CaseDocument).where(CaseDocument.case_id == case.id, CaseDocument.role == CaseDocumentRole.CLAIM)
            )
        ).scalars().all()
        results: list[tuple[uuid.UUID, str, str]] = []
        for cd in claim_case_documents:
            document = await self._session.get(Document, cd.document_id)
            if document is not None:
                results.append((document.id, document.title, document.extracted_text or ""))
        return results

    async def _correspondence_document_texts(self, case: Case) -> list[tuple[uuid.UUID, str, str]]:
        """(document_id, title, extracted_text) for every CORRESPONDENCE-role
        document — a pre-suit demand letter (with any attached delivery-
        tracking report) is generically correspondence between the parties,
        same fetch shape as `_claim_document_texts`.
        """
        correspondence_case_documents = (
            await self._session.execute(
                select(CaseDocument).where(CaseDocument.case_id == case.id, CaseDocument.role == CaseDocumentRole.CORRESPONDENCE)
            )
        ).scalars().all()
        results: list[tuple[uuid.UUID, str, str]] = []
        for cd in correspondence_case_documents:
            document = await self._session.get(Document, cd.document_id)
            if document is not None:
                results.append((document.id, document.title, document.extracted_text or ""))
        return results

    async def get_master_report(self, case: Case) -> MasterCaseReport:
        """Top-level synthesis — zero LLM calls, everything below is a
        template rule keyed off already-persisted structured data. See
        master_report.py's module docstring for the full discipline.
        """
        our_side_role = await self._determine_our_side_role(case)

        allegation_rows = (
            await self._session.execute(select(CaseAllegation).where(CaseAllegation.case_id == case.id))
        ).scalars().all()
        allegation_inputs = [
            AllegationInput(
                id=a.id, document_id=a.document_id, page_number=a.page_number, excerpt=a.excerpt, allegation_type=a.allegation_type
            )
            for a in allegation_rows
        ]
        allegation_types_present = {a.allegation_type for a in allegation_rows}

        claim_evidence_contradictions = await self.get_claim_evidence_contradictions(case)
        claim_theory_tensions = detect_claim_theory_tensions(allegation_inputs)

        contract_case_documents = (
            await self._session.execute(
                select(CaseDocument).where(CaseDocument.case_id == case.id, CaseDocument.role == CaseDocumentRole.CONTRACT)
            )
        ).scalars().all()
        contract_documents: list[tuple[uuid.UUID, str, str]] = []
        for cd in contract_case_documents:
            document = await self._session.get(Document, cd.document_id)
            if document is not None:
                contract_documents.append((document.id, document.title, document.extracted_text or ""))
        contract_version_matrix = build_contract_version_matrix(contract_documents)

        money_flow = await self.get_money_flow(case)
        payment_pattern = detect_payment_pattern(
            [t.payment_date for t in money_flow.transactions if t.payment_date is not None],
            [t.payer for t in money_flow.transactions],
            [t.recipient for t in money_flow.transactions],
        )

        party_relationship_findings = await self.get_party_relationship_findings(case)
        result_summary = await self.get_result_summary(case)

        related_litigation_rows = (
            await self._session.execute(select(CaseRelatedLitigation).where(CaseRelatedLitigation.case_id == case.id))
        ).scalars().all()
        related_litigation_inputs = [
            RelatedLitigationInput(
                id=r.id, case_number=r.case_number, court=r.court, subject_matter=r.subject_matter,
                amount_in_dispute=r.amount_in_dispute,
            )
            for r in related_litigation_rows
        ]

        document_ids = (
            {a.document_id for a in allegation_rows}
            | {t[0] for t in contract_documents}
            | {f.source_document_id for f in party_relationship_findings if f.source_document_id}
            | {i.source_document_id for i in result_summary.missing_critical_evidence if i.source_document_id}
        )
        document_titles: dict[uuid.UUID, str] = {}
        for document_id in document_ids:
            document = await self._session.get(Document, document_id)
            if document is not None:
                document_titles[document_id] = document.title

        findings = build_claim_contradiction_findings(claim_evidence_contradictions, claim_theory_tensions, document_titles, our_side_role)
        payment_finding = build_payment_pattern_finding(payment_pattern)
        if payment_finding is not None:
            findings.append(payment_finding)
        mismatch_finding = build_contract_mismatch_finding(contract_version_matrix, money_flow.total_amount)
        if mismatch_finding is not None:
            findings.append(mismatch_finding)
        findings.extend(build_contract_formation_findings(contract_version_matrix))
        findings.extend(build_evidence_gap_findings(result_summary.missing_critical_evidence))
        findings.extend(build_corporate_relationship_findings(party_relationship_findings))
        findings.extend(build_related_litigation_findings(related_litigation_inputs))

        course_of_dealing_result = detect_course_of_dealing(money_flow.referenced_contract_dates, contract_version_matrix)
        course_of_dealing_finding = build_course_of_dealing_finding(course_of_dealing_result)
        if course_of_dealing_finding is not None:
            findings.append(course_of_dealing_finding)

        theory_vs_conduct_finding = build_theory_vs_conduct_finding(allegation_types_present, payment_pattern)
        if theory_vs_conduct_finding is not None:
            findings.append(theory_vs_conduct_finding)

        claim_document_texts = [text for _id, _title, text in await self._claim_document_texts(case)]
        earliest_payment_date = min(
            (t.payment_date for t in money_flow.transactions if t.payment_date is not None), default=None
        )
        contract_maturity_dates = [d for terms in contract_version_matrix for d in terms.maturity_dates]
        interest_finding = None
        latest_parseable_maturity_date = None
        for claim_text in claim_document_texts:
            interest_claim = extract_interest_claim(claim_text, earliest_payment_date, contract_maturity_dates)
            if interest_claim is not None:
                interest_finding = build_interest_damages_finding(interest_claim)
                latest_parseable_maturity_date = interest_claim.latest_parseable_maturity_date
                break
        if interest_finding is not None:
            findings.append(interest_finding)

        # --- Part 2: structured per-installment interest table ---
        earliest_interest_start = None
        for claim_text in claim_document_texts:
            interest_table = extract_interest_calculation_table(claim_text)
            if interest_table.row_count > 0:
                earliest_interest_start = interest_table.earliest_interest_start
                interest_table_finding = build_interest_table_finding(interest_table)
                if interest_table_finding is not None:
                    findings.append(interest_table_finding)
                break
        if earliest_interest_start is None and claim_document_texts:
            first_claim = extract_interest_claim(claim_document_texts[0], earliest_payment_date, contract_maturity_dates)
            earliest_interest_start = first_claim.period_start if first_claim is not None else None

        # --- Part 4: demand/notice delivery timeline ---
        correspondence_texts = [text for _id, _title, text in await self._correspondence_document_texts(case)]
        notice_result = None
        for text in correspondence_texts:
            candidate = extract_notice_timeline(text)
            if candidate.tracking_report_present:
                notice_result = candidate
                break
        if notice_result is None and correspondence_texts:
            notice_result = extract_notice_timeline(correspondence_texts[0])
        if notice_result is not None:
            notice_finding = build_notice_timeline_finding(notice_result)
            if notice_finding is not None:
                findings.append(notice_finding)

        # --- Part 3: temporal reasoning + Part 5: cross-finding synthesis ---
        claim_document_date = extract_document_own_date(claim_document_texts[0]) if claim_document_texts else None
        temporal_issues = analyze_temporal_issues(
            earliest_interest_start=earliest_interest_start,
            latest_maturity_date=latest_parseable_maturity_date,
            demand_date=notice_result.demand_date if notice_result is not None else None,
            demand_tracking_present=notice_result.tracking_report_present if notice_result is not None else False,
            demand_final_status=notice_result.final_status if notice_result is not None else "UNKNOWN",
            claim_document_date=claim_document_date,
        )
        temporal_findings = build_temporal_issue_findings(temporal_issues)
        findings.extend(temporal_findings)
        timing_synthesis = build_timing_synthesis_finding(temporal_findings)
        if timing_synthesis is not None:
            findings.append(timing_synthesis)

        credibility_synthesis = build_credibility_synthesis_finding(
            allegation_types_present, payment_pattern, party_relationship_findings, earliest_payment_date
        )
        if credibility_synthesis is not None:
            findings.append(credibility_synthesis)

        findings = rank_findings(findings)

        claim_contradiction_findings = [f for f in findings if f.category.value == "claim_contradiction"]
        burden_map = build_burden_map(allegation_types_present, claim_contradiction_findings, our_side_role)

        claim_amounts, claim_dates = await self._claim_document_facts(case)
        case_map = build_case_map(claim_amounts, claim_dates)

        court_scenarios = build_court_scenarios(findings)
        opposing_party_questions = build_opposing_party_questions(findings)
        draft_response_structure = build_draft_response_structure(findings)
        next_best_action = result_summary.next_best_actions[0].action if result_summary.next_best_actions else None
        one_pager = build_one_pager(findings, money_flow.total_amount, next_best_action)

        return MasterCaseReport(
            one_pager=one_pager, case_map=case_map, findings=findings, burden_map=burden_map,
            court_scenarios=court_scenarios, opposing_party_questions=opposing_party_questions,
            draft_response_structure=draft_response_structure, contract_version_matrix=contract_version_matrix,
            money_flow=money_flow, legal_kb_warning=result_summary.legal_kb_warning,
        )
