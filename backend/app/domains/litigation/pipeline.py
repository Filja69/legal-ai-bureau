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
from dataclasses import dataclass
from datetime import date

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.litigation.allegation_extractor import ALLEGATION_ELIGIBLE_ROLES, extract_allegation_candidates
from app.domains.litigation.case_result_summary import CaseResultSummary, build_case_result_summary
from app.domains.litigation.contradiction_detector import (
    AllegationInput,
    ClaimEvidenceContradiction,
    ContradictionCandidate,
    PaymentOrderInput,
    detect_claim_vs_evidence_contradictions,
    detect_contradictions,
)
from app.domains.litigation.evidence_matrix import EvidenceMatrixRow, build_evidence_matrix
from app.domains.litigation.fact_dedup import CanonicalFact, deduplicate_facts
from app.domains.litigation.fact_extractor import FactEvidenceCandidate, extract_fact_candidates
from app.domains.litigation.payment_extractor import extract_payment_order_candidate
from app.domains.litigation.timeline_builder import build_timeline
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
    CaseParty,
    CasePaymentOrder,
    Document,
    DocumentChunk,
    DocumentStatus,
    FactStatus,
    FactType,
    PaymentExecutionStatus,
)

logger = structlog.get_logger(__name__)


@dataclass
class MoneyFlowTransaction:
    payment_order_id: uuid.UUID
    document_id: uuid.UUID
    payment_date: date | None
    amount: str | None
    payer: str | None
    recipient: str | None
    referenced_contract_date: date | None


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
        """Computed at read time from CasePaymentOrder rows — a total and a
        grouping of referenced contract dates/numbers ONLY as a count of how
        many payments cite each one. Deliberately does not merge same-dated
        payments into "one obligation" — see payment_extractor.py's module
        docstring on why that's a candidate-linkage question, not a fact.
        """
        payment_orders = (
            await self._session.execute(
                select(CasePaymentOrder).where(CasePaymentOrder.case_id == case.id).order_by(CasePaymentOrder.payment_date)
            )
        ).scalars().all()

        transactions = [
            MoneyFlowTransaction(
                payment_order_id=p.id, document_id=p.document_id, payment_date=p.payment_date, amount=p.amount,
                payer=p.payer, recipient=p.recipient, referenced_contract_date=p.referenced_contract_date,
            )
            for p in payment_orders
        ]

        total = sum((float(p.amount) for p in payment_orders if p.amount is not None), 0.0)

        dates: dict[str, int] = {}
        numbers: dict[str, int] = {}
        for p in payment_orders:
            if p.referenced_contract_date is not None:
                key = p.referenced_contract_date.isoformat()
                dates[key] = dates.get(key, 0) + 1
            if p.referenced_contract_number is not None:
                numbers[p.referenced_contract_number] = numbers.get(p.referenced_contract_number, 0) + 1

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
        for document_id in document_ids:
            document = await self._session.get(Document, document_id)
            if document is not None:
                document_titles[document_id] = document.title

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
            kb_is_empty=kb_count == 0,
        )
