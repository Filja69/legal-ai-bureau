from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.domains.litigation.master_report import FindingCategory
from app.models.matters import (
    AllegationType,
    CaseDocumentRole,
    ContradictionType,
    DateType,
    FactStatus,
    FactType,
    HypothesisCategory,
    PartyType,
    PaymentExecutionStatus,
    ProceduralRole,
    RelationshipType,
    RelationshipVerificationStatus,
)


class CasePartyCreate(BaseModel):
    name: str
    party_type: PartyType = PartyType.UNKNOWN
    procedural_role: ProceduralRole = ProceduralRole.UNKNOWN
    identifiers: dict = {}


class CasePartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    name: str
    party_type: PartyType
    procedural_role: ProceduralRole
    identifiers: dict


class CaseDocumentAttach(BaseModel):
    document_id: uuid.UUID
    role: CaseDocumentRole = CaseDocumentRole.OTHER


class CaseDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    role: CaseDocumentRole
    document_title: str
    document_status: str


class CaseFactEvidenceOut(BaseModel):
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID | None
    page_number: int | None
    section_path: str | None
    excerpt: str


class CaseFactOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    statement: str
    fact_type: FactType
    status: FactStatus
    normalized_value: str | None
    evidence: list[CaseFactEvidenceOut]
    created_at: datetime | None = None


class CaseEventOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    event_date: date | None
    date_type: DateType
    description: str
    event_type: str | None
    source_fact_id: uuid.UUID | None


class CaseContradictionOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    contradiction_type: ContradictionType
    description: str
    fact_a_id: uuid.UUID
    fact_a_statement: str
    fact_b_id: uuid.UUID
    fact_b_statement: str


class EvidenceMatrixRowOut(BaseModel):
    fact_statement: str
    fact_type: FactType
    normalized_value: str
    strength: str
    reasons: list[str]
    corroboration_count: int


# --- E1: case allegations ---


class CaseAllegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    chunk_id: uuid.UUID | None
    page_number: int | None
    statement_text: str
    excerpt: str
    allegation_type: AllegationType
    created_at: datetime | None = None


# --- E3: structured payment orders ---


class CasePaymentOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    payment_date: date | None
    amount: str | None
    payer: str | None
    recipient: str | None
    payment_purpose: str | None
    referenced_contract_type: str | None
    referenced_contract_date: date | None
    referenced_contract_number: str | None
    execution_status: PaymentExecutionStatus
    excerpt: str


class MoneyFlowTransactionOut(BaseModel):
    payment_order_id: uuid.UUID
    document_id: uuid.UUID
    payment_date: date | None
    amount: str | None
    payer: str | None
    recipient: str | None
    referenced_contract_date: date | None


class MoneyFlowOut(BaseModel):
    transaction_count: int
    transactions: list[MoneyFlowTransactionOut]
    total_amount: str
    referenced_contract_dates: dict[str, int]
    referenced_contract_numbers: dict[str, int]


# --- E2: CLAIM_VS_EVIDENCE (computed, never persisted) ---


class ClaimEvidenceContradictionOut(BaseModel):
    contradiction_type: ContradictionType
    allegation_id: uuid.UUID
    allegation_document_id: uuid.UUID
    allegation_document_title: str
    allegation_page: int | None
    allegation_excerpt: str
    evidence_id: uuid.UUID
    evidence_document_id: uuid.UUID
    evidence_document_title: str
    evidence_page: int | None
    evidence_excerpt: str
    referenced_contract_date: date | None
    reason: str
    caveat: str
    confidence: str


# --- Case Result Summary (client-facing, template/deterministic synthesis) ---


class CaseSnapshotOut(BaseModel):
    party_names: list[str]
    document_count: int
    payment_count: int
    total_amount: str
    key_dates: list[tuple[date | None, str]]


class KeyFindingOut(BaseModel):
    severity: str
    statement: str
    source_document_id: uuid.UUID
    source_document_title: str
    page_number: int | None
    excerpt: str
    confidence: str
    caveat: str | None


class MissingEvidenceItemOut(BaseModel):
    priority: str
    description: str
    why_it_matters: str
    source_document_id: uuid.UUID | None = None
    source_document_title: str | None = None


class NextBestActionOut(BaseModel):
    priority: int
    action: str
    why: str


class PartyRelationshipFindingOut(BaseModel):
    subject_name: str
    related_party_name: str
    relationship_type: RelationshipType
    relationship_start: date | None
    relationship_end: date | None
    timing_note: str
    why_it_may_matter: str
    what_is_still_needed: list[str]
    verification_status: RelationshipVerificationStatus
    source_document_id: uuid.UUID | None
    source_document_title: str | None
    source_excerpt: str | None


class CaseResultSummaryOut(BaseModel):
    case_snapshot: CaseSnapshotOut
    key_findings: list[KeyFindingOut]
    money_flow: MoneyFlowOut
    what_this_may_mean: list[str]
    missing_critical_evidence: list[MissingEvidenceItemOut]
    next_best_actions: list[NextBestActionOut]
    legal_kb_warning: str | None
    party_relationship_findings: list[PartyRelationshipFindingOut] = []


# --- Case Intelligence: party relationships, hypothesis register, related litigation ---


class CasePartyRelationshipCreate(BaseModel):
    subject_party_id: uuid.UUID
    related_party_id: uuid.UUID
    relationship_type: RelationshipType
    ownership_percentage: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    source_document_id: uuid.UUID | None = None
    source_excerpt: str | None = None
    verification_status: RelationshipVerificationStatus = RelationshipVerificationStatus.UNVERIFIED
    notes: str | None = None


class CasePartyRelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    subject_party_id: uuid.UUID
    related_party_id: uuid.UUID
    relationship_type: RelationshipType
    ownership_percentage: str | None
    start_date: date | None
    end_date: date | None
    source_document_id: uuid.UUID | None
    source_excerpt: str | None
    verification_status: RelationshipVerificationStatus
    notes: str | None


class CaseHypothesisCreate(BaseModel):
    category: HypothesisCategory
    statement: str
    required_verification: list[str] = []
    related_relationship_id: uuid.UUID | None = None
    source: str | None = None


class CaseHypothesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    category: HypothesisCategory
    statement: str
    required_verification: list[str]
    related_relationship_id: uuid.UUID | None
    source: str | None


class CaseRelatedLitigationCreate(BaseModel):
    court: str | None = None
    case_number: str | None = None
    parties_description: str | None = None
    subject_matter: str | None = None
    amount_in_dispute: str | None = None
    status: str | None = None
    note: str | None = None


class CaseRelatedLitigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID
    court: str | None
    case_number: str | None
    parties_description: str | None
    subject_matter: str | None
    amount_in_dispute: str | None
    status: str | None
    note: str | None
    # Computed at read time, never stored verbatim as a causal claim — see
    # case_relationships.py's build_related_litigation_note().
    contextual_note: str


# --- Master Case Report ---


class MasterFindingOut(BaseModel):
    id: str
    category: FindingCategory
    title: str
    statement: str
    supporting_facts: list[str]
    contradicting_facts: list[str]
    source_document_ids: list[uuid.UUID]
    source_document_titles: list[str]
    excerpts: list[str]
    page_numbers: list[int | None]
    helps_side: str
    hurts_side: str
    strength: str
    confidence: str
    legal_significance: str
    counterargument: str | None
    response_to_counterargument: str | None
    caveat: str | None
    missing_evidence: list[str]
    recommended_action: str | None
    verification_status: str


class CaseOnePagerOut(BaseModel):
    case_position: str
    strongest_point: str | None
    biggest_risk: str | None
    money_at_stake: str
    top_arguments: list[str]
    top_risks: list[str]
    what_opponent_must_explain: list[str]
    what_court_likely_focuses_on: str | None
    missing_p0_evidence: list[str]
    next_best_action: str | None


class CourtScenarioOut(BaseModel):
    scenario: str
    why_court_could_get_there: str
    facts_supporting: list[str]
    facts_against: list[str]
    label: str


class DraftResponseSectionOut(BaseModel):
    section: str
    argument: str
    supporting_finding_ids: list[str]
    caution: str | None


class BurdenItemOut(BaseModel):
    proposition: str
    side: str
    current_evidence: list[str]
    contrary_evidence: list[str]
    status: str
    weakness: str | None
    how_to_attack: str | None


class CaseMapOut(BaseModel):
    claimed_amounts: list[str]
    claim_dates: list[str]
    note: str


class ContractVersionTermsOut(BaseModel):
    document_id: uuid.UUID
    document_title: str
    amounts: list[str]
    interest_rate: str | None
    maturity_dates: list[str]
    formation_clause_present: bool
    signature_status: str


class MasterCaseReportOut(BaseModel):
    one_pager: CaseOnePagerOut
    case_map: CaseMapOut
    findings: list[MasterFindingOut]
    burden_map: list[BurdenItemOut]
    court_scenarios: list[CourtScenarioOut]
    opposing_party_questions: list[str]
    draft_response_structure: list[DraftResponseSectionOut]
    contract_version_matrix: list[ContractVersionTermsOut]
    money_flow: MoneyFlowOut
    legal_kb_warning: str | None
