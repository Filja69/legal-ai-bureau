"""Tenant-scoped matter-management entities: Case, Document, Evidence,
LegalIssue, LegalRisk. Every table here is workspace-scoped (LEGAL-SECURITY.md §2) —
reached only via Workspace, never a bare user_id.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config.settings import get_settings
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum, workspace_fk

_EMBEDDING_DIMENSION = get_settings().embedding_dimension


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    RESEARCH = "research"
    DRAFTING = "drafting"
    LITIGATION = "litigation"
    CLOSED = "closed"


class Case(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cases"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(pg_enum(CaseStatus), default=CaseStatus.OPEN)
    client_name: Mapped[str | None] = mapped_column(String(255))
    counterparty_name: Mapped[str | None] = mapped_column(String(255))
    matter_type: Mapped[str | None] = mapped_column(String(64))


class DocumentType(str, enum.Enum):
    CONTRACT = "contract"
    EVIDENCE = "evidence"
    CORRESPONDENCE = "correspondence"
    GENERATED = "generated"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    """Phase 9.2 — real pipeline states, replacing the Phase 8 placeholder
    that only ever showed "uploaded". `OCR_REQUIRED` is an honest terminal
    state, not a failure: a scanned PDF with no text layer is not something
    this phase's extractors can read, and pretending otherwise (e.g. sending
    the page image to an LLM and calling it "extraction") is exactly the
    kind of fabrication this project refuses to do. `UNSUPPORTED` is for a
    file type that validation should have already rejected before storage,
    but is listed as a status too so an existing row can honestly reflect it.
    """

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    OCR_REQUIRED = "ocr_required"
    UNSUPPORTED = "unsupported"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-owned uploaded/generated document. Not to be confused with the
    shared-knowledge-base `LegalDocument` (app/models/legal_knowledge.py).
    """

    __tablename__ = "documents"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(pg_enum(DocumentType), default=DocumentType.OTHER)
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Phase 9.2 — real upload/processing pipeline fields.
    original_filename: Mapped[str | None] = mapped_column(String(512))
    media_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[DocumentStatus] = mapped_column(pg_enum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column()


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-scoped searchable representation of a `Document`'s extracted
    text — structurally distinct from `EmbeddingChunk` (app/models/
    embedding_chunk.py), which indexes ONLY the public Legal Knowledge Base
    and has no `workspace_id` column at all. That absence is what makes
    public-KB leakage across tenants structurally impossible (see the test
    `test_public_legal_kb_has_no_workspace_column`); this table is the
    mirror-image guarantee for tenant documents — every row is
    workspace-scoped and NOT NULL, so a query that forgets to filter by
    workspace_id fails to compile against `WorkspaceScopedRepository`
    conventions rather than silently returning another tenant's data
    (Phase 9.2 brief §14 — these two indexes must never be merged).
    """

    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("workspace_id", "document_id", "chunk_index", name="uq_document_chunk_position"),)

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(512))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)

    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIMENSION), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_namespace: Mapped[str] = mapped_column(String(200), nullable=False, index=True)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Backs the Evidence Matrix — LEGAL-DATABASE.md §5."""

    __tablename__ = "evidence"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    claim_supported: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_type: Mapped[str | None] = mapped_column(String(64))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    availability: Mapped[str] = mapped_column(String(16), default="missing")  # available|missing
    strength: Mapped[str | None] = mapped_column(String(16))  # low|medium|high


class LegalIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A legal question/issue identified during the reasoning pipeline
    (LEGAL-AGENTS.md §2, ISSUE IDENTIFICATION step) for a given case/research report.
    """

    __tablename__ = "legal_issues"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    article_refs: Mapped[dict] = mapped_column(JSONB, default=list)


class RiskSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LegalRisk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Risk Matrix entry — LEGAL-DATABASE.md §5 (`RiskItem`)."""

    __tablename__ = "legal_risks"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)  # contract|case|company
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    clause_reference: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[RiskSeverity] = mapped_column(pg_enum(RiskSeverity), nullable=False)
    probability: Mapped[str | None] = mapped_column(String(16))
    impact: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64))
    explanation: Mapped[str | None] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)
    source_citation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("citations.id"))


class ResearchReportStatus(str, enum.Enum):
    COMPLETED = "completed"
    BLOCKED_UNVERIFIED_CLAIM = "blocked_unverified_claim"
    RESEARCH_FAILED = "research_failed"


class LegalResearchReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted LegalResearchEngine output (Phase 8 — previously
    compute-and-return only, per the Phase 3 revision note in
    app/api/v1/research.py). Lets the Research workspace list past research
    and reopen a result instead of only ever showing the response of the
    single most recent call. `result_json`/`trace_json` are the exact same
    serialized shapes POST /research already returns — no new schema, just
    persistence of what already existed.
    """

    __tablename__ = "legal_research_reports"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), default="RU")
    status: Mapped[ResearchReportStatus] = mapped_column(pg_enum(ResearchReportStatus), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    executive_conclusion: Mapped[str] = mapped_column(Text, default="")
    escalate_to_human: Mapped[bool] = mapped_column(default=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    trace_json: Mapped[dict] = mapped_column(JSONB, nullable=False)


# --- Phase 9.3: Litigation & Case Intelligence — bounded slice (brief §2/§48:
# parties, document linking, facts-with-provenance, timeline, contradictions.
# Deliberately NOT built this phase: claims/defenses tables, persisted issue
# trees, opponent-model/strategy/draft tables — see docs/PHASE-9-3-LITIGATION-RESULT.md
# for the explicit scope decision. Evidence Matrix and legal-issue linkage are
# computed on read from CaseFact/CaseFactEvidence rather than persisted as a
# separate redundant table, to avoid the schema explosion the brief warns
# against (§48 "Avoid schema explosion merely because the brief lists concepts"). ---


class PartyType(str, enum.Enum):
    INDIVIDUAL = "individual"
    ORGANIZATION = "organization"
    UNKNOWN = "unknown"


class ProceduralRole(str, enum.Enum):
    PLAINTIFF = "plaintiff"
    DEFENDANT = "defendant"
    THIRD_PARTY = "third_party"
    APPLICANT = "applicant"
    RESPONDENT = "respondent"
    UNKNOWN = "unknown"


class CaseParty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §5 — procedural role is never inferred with unwarranted confidence;
    `UNKNOWN` is the honest default until a document/user establishes it.
    """

    __tablename__ = "case_parties"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    party_type: Mapped[PartyType] = mapped_column(pg_enum(PartyType), default=PartyType.UNKNOWN)
    procedural_role: Mapped[ProceduralRole] = mapped_column(pg_enum(ProceduralRole), default=ProceduralRole.UNKNOWN)
    identifiers: Mapped[dict] = mapped_column(JSONB, default=dict)
    party_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)


class CaseDocumentRole(str, enum.Enum):
    CONTRACT = "contract"
    ADDENDUM = "addendum"
    INVOICE = "invoice"
    ACT = "act"
    CORRESPONDENCE = "correspondence"
    CLAIM = "claim"
    RESPONSE = "response"
    COURT_FILING = "court_filing"
    COURT_DECISION = "court_decision"
    EXPERT_REPORT = "expert_report"
    PAYMENT_DOCUMENT = "payment_document"
    OTHER = "other"


class CaseDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links an existing (Phase 9.2) `Document` into a `Case` — never
    duplicates the uploaded file (brief §6). `role` is deliberately a
    litigation-specific vocabulary distinct from `DocumentType`, and is
    never confused with legal authority (brief §6/§18: a `COURT_DECISION`
    role here is still the client's own filed/received copy — evidence —
    not the same thing as a `CourtDecision` row in the public case-law table).
    """

    __tablename__ = "case_documents"
    __table_args__ = (UniqueConstraint("case_id", "document_id", name="uq_case_document"),)

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[CaseDocumentRole] = mapped_column(pg_enum(CaseDocumentRole), default=CaseDocumentRole.OTHER)


class FactStatus(str, enum.Enum):
    """brief §7 — evidence support determines status, never LLM confidence
    alone. Only the fact-extraction pipeline assigns `SUPPORTED`, and only
    when a real `CaseFactEvidence` row with real document provenance backs
    it (see `app/domains/litigation/fact_extractor.py`).
    """

    ASSERTED = "asserted"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    CONTRADICTED = "contradicted"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class FactType(str, enum.Enum):
    DATE = "date"
    AMOUNT = "amount"
    PARTY = "party"
    EVENT = "event"
    OTHER = "other"


class CaseFact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "case_facts"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    fact_type: Mapped[FactType] = mapped_column(pg_enum(FactType), default=FactType.OTHER)
    status: Mapped[FactStatus] = mapped_column(pg_enum(FactStatus), default=FactStatus.UNKNOWN)
    # Canonical dedup key (brief §9) — e.g. "2026-03-14" for a date fact,
    # "500000.00" for an amount fact. Two facts sharing a `normalized_value`
    # + `fact_type` within one case are the same canonical fact with
    # multiple evidence rows, not two unrelated facts.
    normalized_value: Mapped[str | None] = mapped_column(String(128), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)


class CaseFactEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §8 — every SUPPORTED fact must trace to a real DocumentChunk;
    a fact can have multiple evidence rows (brief §9's "Canonical Fact ->
    Evidence A/B/C") when several documents independently state it.
    """

    __tablename__ = "case_fact_evidence"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_facts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"))
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(512))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)


class DateType(str, enum.Enum):
    """brief §11 — only EXACT and UNKNOWN are actually produced this phase;
    CALCULATED (deriving a date from a rule like "within 10 business days
    of delivery") and APPROXIMATE are modeled in the schema for forward
    compatibility but no code path emits them yet — see
    docs/PHASE-9-3-LITIGATION-RESULT.md for the explicit scope note.
    """

    EXACT = "exact"
    CALCULATED = "calculated"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class CaseEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "case_events"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    event_date: Mapped[date | None] = mapped_column(Date)
    date_type: Mapped[DateType] = mapped_column(pg_enum(DateType), default=DateType.UNKNOWN)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(64))
    source_fact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("case_facts.id", ondelete="SET NULL"))
    # Added for the Case Intelligence layer (party relationships) — mirrors
    # source_fact_id exactly, lets a relationship-derived event (e.g.
    # "shareholder_change") populate the timeline without a synthetic
    # CaseFact and without touching timeline_builder.py/build_timeline() at
    # all. Exactly one of source_fact_id/source_relationship_id is set in
    # practice, but this is a convention enforced by the writers, not a DB
    # constraint — either can legitimately be absent (e.g. a manually added event).
    source_relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_party_relationships.id", ondelete="SET NULL")
    )


class ContradictionType(str, enum.Enum):
    DATE_MISMATCH = "date_mismatch"
    AMOUNT_MISMATCH = "amount_mismatch"
    PARTY_MISMATCH = "party_mismatch"
    # Not written to case_contradictions.contradiction_type (no DB enum value,
    # no migration) — this row is a Python-only value used exclusively by the
    # CLAIM_VS_EVIDENCE dataclass computed at read time (see
    # app/domains/litigation/contradiction_detector.py's
    # detect_claim_vs_evidence_contradictions and pipeline.py's
    # get_claim_evidence_contradictions), the same "computed, not persisted"
    # pattern already used for EvidenceMatrixRow.
    CLAIM_VS_EVIDENCE = "claim_vs_evidence"
    OTHER = "other"


class CaseContradiction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §14 — deterministic contradiction detection between two
    canonical `CaseFact` rows of the same `fact_type` but different
    `normalized_value`, sourced from different documents.
    """

    __tablename__ = "case_contradictions"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    contradiction_type: Mapped[ContradictionType] = mapped_column(pg_enum(ContradictionType), default=ContradictionType.OTHER)
    fact_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_facts.id", ondelete="CASCADE"), nullable=False)
    fact_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_facts.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


# --- E1-E4 (litigation evidence layer, curated-dataset-task companion brief):
# case allegations (claims asserted BY a party in a pleading) and structured
# payment-order facts. Both are deterministic-regex-extracted with the same
# real-provenance discipline as CaseFact/CaseFactEvidence — nothing here is
# ever LLM-inferred. CLAIM_VS_EVIDENCE contradictions between the two are
# computed at read time (see ContradictionType.CLAIM_VS_EVIDENCE above),
# never persisted as a CaseContradiction row, so no schema/enum change was
# needed there. ---


class AllegationType(str, enum.Enum):
    """Deliberately narrow (brief: "Do NOT attempt open-ended LLM allegation
    extraction yet") — five bounded categories, each backed by an explicit,
    documented Russian regex pattern in
    app/domains/litigation/allegation_extractor.py, not a free-text summary.
    """

    NO_CONTRACT = "no_contract"
    NO_LEGAL_BASIS = "no_legal_basis"
    UNJUST_ENRICHMENT = "unjust_enrichment"
    PAYMENT_BY_MISTAKE = "payment_by_mistake"
    FUTURE_CONTRACT_NEGOTIATIONS = "future_contract_negotiations"


class CaseAllegation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A claim/assertion literally found in a party's own pleading text
    (typically a CLAIM/COURT_FILING/RESPONSE-role CaseDocument) — never an
    LLM's summary of what a document "means". `statement_text` is the
    matched sentence-level text; `excerpt` is the same bounded-radius
    excerpt convention as CaseFactEvidence, for consistent UI rendering.
    """

    __tablename__ = "case_allegations"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"))
    page_number: Mapped[int | None] = mapped_column(Integer)
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    allegation_type: Mapped[AllegationType] = mapped_column(pg_enum(AllegationType), nullable=False)


class PaymentExecutionStatus(str, enum.Enum):
    EXECUTED = "executed"
    UNKNOWN = "unknown"


class CasePaymentOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per PAYMENT_DOCUMENT-role CaseDocument — structured fields
    extracted deterministically from the payment order's own text, never
    inferred. `referenced_contract_date`/`referenced_contract_number` are
    exactly what the payment's own "Назначение платежа" text says, nothing
    more — see app/domains/litigation/payment_extractor.py's module
    docstring for why matching contract dates across payments is never
    auto-treated as proof they're the same legal obligation.
    """

    __tablename__ = "case_payment_orders"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="SET NULL"))
    page_number: Mapped[int | None] = mapped_column(Integer)

    payment_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[str | None] = mapped_column(String(32))  # decimal-as-string, same convention as CaseFact.normalized_value
    payer: Mapped[str | None] = mapped_column(String(255))
    recipient: Mapped[str | None] = mapped_column(String(255))
    payment_purpose: Mapped[str | None] = mapped_column(Text)
    referenced_contract_type: Mapped[str | None] = mapped_column(String(128))
    referenced_contract_date: Mapped[date | None] = mapped_column(Date)
    referenced_contract_number: Mapped[str | None] = mapped_column(String(64))
    execution_status: Mapped[PaymentExecutionStatus] = mapped_column(
        pg_enum(PaymentExecutionStatus), default=PaymentExecutionStatus.UNKNOWN
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)


# --- Party relationships, hypothesis register, related litigation (Case
# Intelligence layer built on top of E1-E4 — party/corporate relationships,
# a unified event timeline, temporal analysis, and explicit fact/hypothesis
# discipline). Deliberately reuses CaseParty as both endpoints of a
# relationship (a person and the entity they're linked to) rather than
# adding separate Person/LegalEntity tables — CaseParty.party_type already
# distinguishes them. Nothing here infers actual knowledge/intent from
# relationship status alone; see case_relationships.py's module docstring. ---


class RelationshipType(str, enum.Enum):
    """DIRECTOR/SHAREHOLDER/MEMBER cover the two distinct Russian corporate
    forms this matters for: акционер (АО, "shareholder") vs участник (ООО,
    "member") — deliberately not collapsed into one value, since which one
    applies is itself a fact worth getting right, not a detail to blur.
    """

    DIRECTOR = "director"
    SHAREHOLDER = "shareholder"
    MEMBER = "member"
    OTHER = "other"


class RelationshipVerificationStatus(str, enum.Enum):
    """brief: never silently promote a relationship claim's confidence.
    UNVERIFIED is the only status this domain's own extraction ever sets —
    DOCUMENT_SUPPORTED/EXTERNALLY_VERIFIED/CONFLICTING exist for a human
    (or a future verification step) to set explicitly, never inferred.
    """

    UNVERIFIED = "unverified"
    DOCUMENT_SUPPORTED = "document_supported"
    EXTERNALLY_VERIFIED = "externally_verified"
    CONFLICTING = "conflicting"


class CasePartyRelationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A claimed relationship between two CaseParty rows (e.g. "person X is
    director of entity Y") — always carries real provenance (source_document_id
    + source_excerpt) and a verification_status that starts UNVERIFIED and is
    never auto-upgraded. `subject_party_id` is the party WHO HOLDS the role;
    `related_party_id` is the entity the role is IN.
    """

    __tablename__ = "case_party_relationships"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_parties.id", ondelete="CASCADE"), nullable=False
    )
    related_party_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_parties.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(pg_enum(RelationshipType), nullable=False)
    # decimal-as-string, e.g. "25.00" — never computed, only transcribed
    ownership_percentage: Mapped[str | None] = mapped_column(String(16))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    verification_status: Mapped[RelationshipVerificationStatus] = mapped_column(
        pg_enum(RelationshipVerificationStatus), default=RelationshipVerificationStatus.UNVERIFIED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)


class HypothesisCategory(str, enum.Enum):
    """The one rule this whole layer exists to enforce: a claim is always
    tagged with where it came from and how sure anyone can be of it — never
    silently treated as more established than it is. FACT requires the same
    real-provenance discipline as CaseFact.SUPPORTED; COUNSEL_HYPOTHESIS is
    exactly what outside counsel asserted, verbatim in intent, never
    rephrased into a stronger claim; AI_INFERENCE is this system's own
    derived observation (e.g. a temporal-overlap note), always carrying its
    own caveat; MISSING_EVIDENCE names a gap, not a claim.
    """

    FACT = "fact"
    COUNSEL_HYPOTHESIS = "counsel_hypothesis"
    AI_INFERENCE = "ai_inference"
    MISSING_EVIDENCE = "missing_evidence"


class CaseHypothesis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "case_hypotheses"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[HypothesisCategory] = mapped_column(pg_enum(HypothesisCategory), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    # JSONB list[str] of what would be needed to move this toward FACT — e.g.
    # ["EGRUL history", "участников reestr", "переписка о доступе к информации"].
    required_verification: Mapped[list] = mapped_column(JSONB, default=list)
    related_relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_party_relationships.id", ondelete="SET NULL")
    )
    # e.g. "counsel", "system" — free text, not an enum: who said this is
    # metadata, not a claim needing verification discipline.
    source: Mapped[str | None] = mapped_column(String(64))


class CaseRelatedLitigation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Another court matter attached as CONTEXT only — never a claimed cause
    of the current case. `note` must never assert causation (enforced in
    case_relationships.py's synthesis layer, not here); this table only
    stores what counsel reported about the other matter.
    """

    __tablename__ = "case_related_litigation"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    court: Mapped[str | None] = mapped_column(String(255))
    case_number: Mapped[str | None] = mapped_column(String(128))
    parties_description: Mapped[str | None] = mapped_column(Text)
    subject_matter: Mapped[str | None] = mapped_column(Text)
    amount_in_dispute: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(Text)
