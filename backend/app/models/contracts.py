"""Contract Intelligence domain models (Phase 4 brief §3-9, §14, §19-21,
§30-31, §35-39, §41, §47). All tenant-scoped (workspace_id), separate from
the shared public Legal Knowledge Base (app/models/legal_knowledge.py) and
from the generic cross-cutting `LegalRisk` (app/models/matters.py) — a
`ContractRisk` row carries substantially more contract-specific structure
(legal_basis, why_it_matters, party perspective, research linkage) than the
generic risk-matrix entry, so it is its own table rather than an overload.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, pg_enum, workspace_fk


class ContractType(str, enum.Enum):
    SERVICE = "service"
    SUPPLY = "supply"
    SALE = "sale"
    LEASE = "lease"
    EMPLOYMENT = "employment"
    NDA = "nda"
    LICENSE = "license"
    LOAN = "loan"
    AGENCY = "agency"
    DISTRIBUTION = "distribution"
    PARTNERSHIP = "partnership"
    SOFTWARE = "software"
    OTHER = "other"
    UNKNOWN = "unknown"


class ContractTypeSource(str, enum.Enum):
    """brief §5 — AI never presents a guess as a confirmed fact."""

    AI_DETECTED = "ai_detected"
    USER_CONFIRMED = "user_confirmed"
    UNKNOWN = "unknown"


class ContractStatus(str, enum.Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ANALYSIS_FAILED = "analysis_failed"


class PartyRole(str, enum.Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    CONTRACTOR = "contractor"
    EMPLOYER = "employer"
    EMPLOYEE = "employee"
    LANDLORD = "landlord"
    TENANT = "tenant"
    LICENSOR = "licensor"
    LICENSEE = "licensee"
    OTHER = "other"


class ClauseType(str, enum.Enum):
    DEFINITIONS = "definitions"
    SUBJECT = "subject"
    PRICE = "price"
    PAYMENT = "payment"
    DELIVERY = "delivery"
    ACCEPTANCE = "acceptance"
    WARRANTY = "warranty"
    LIABILITY = "liability"
    PENALTY = "penalty"
    INDEMNITY = "indemnity"
    FORCE_MAJEURE = "force_majeure"
    TERM = "term"
    RENEWAL = "renewal"
    TERMINATION = "termination"
    CONFIDENTIALITY = "confidentiality"
    PERSONAL_DATA = "personal_data"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    LICENSE = "license"
    NON_COMPETE = "non_compete"
    NON_SOLICIT = "non_solicit"
    DISPUTE_RESOLUTION = "dispute_resolution"
    JURISDICTION = "jurisdiction"
    GOVERNING_LAW = "governing_law"
    AUDIT = "audit"
    INSURANCE = "insurance"
    ASSIGNMENT = "assignment"
    CHANGE_OF_CONTROL = "change_of_control"
    NOTICE = "notice"
    OTHER = "other"


class Contract(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contracts"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    contract_type: Mapped[ContractType] = mapped_column(pg_enum(ContractType), default=ContractType.UNKNOWN)
    contract_type_source: Mapped[ContractTypeSource] = mapped_column(pg_enum(ContractTypeSource), default=ContractTypeSource.UNKNOWN)
    governing_law: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(8))
    language: Mapped[str] = mapped_column(String(8), default="ru")
    status: Mapped[ContractStatus] = mapped_column(pg_enum(ContractStatus), default=ContractStatus.DRAFT)
    contract_date: Mapped[str | None] = mapped_column(String(16))
    effective_date: Mapped[str | None] = mapped_column(String(16))
    expiration_date: Mapped[str | None] = mapped_column(String(16))
    is_mock: Mapped[bool] = mapped_column(default=False)


class ContractVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §4 — analysis is always against a specific version, never a bare document."""

    __tablename__ = "contract_versions"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id"))
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    is_current: Mapped[bool] = mapped_column(default=True)


class ContractParty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_parties"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    party_type: Mapped[str | None] = mapped_column(String(32))  # legal_entity | individual | sole_proprietor
    role: Mapped[PartyRole] = mapped_column(pg_enum(PartyRole), default=PartyRole.OTHER)
    inn: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(8))
    address: Mapped[str | None] = mapped_column(String(1024))
    signatory: Mapped[str | None] = mapped_column(String(255))


class ContractClause(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §8, §11 — original_text is immutable and always traceable back to
    the source document; normalized_text is only ever a whitespace/encoding
    cleanup of it, never a paraphrase.
    """

    __tablename__ = "contract_clauses"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"),
        nullable=False, index=True)
    parent_clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_clauses.id"))
    clause_number: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(255))
    clause_type: Mapped[ClauseType] = mapped_column(pg_enum(ClauseType), default=ClauseType.OTHER)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    position_start: Mapped[int] = mapped_column(Integer, nullable=False)
    position_end: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(default=1.0)


class ContractObligation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §14-16."""

    __tablename__ = "contract_obligations"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    clause_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False)
    party: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(512), nullable=False)
    object: Mapped[str | None] = mapped_column(String(512))
    deadline: Mapped[str | None] = mapped_column(String(255))
    condition: Mapped[str | None] = mapped_column(String(512))
    consequence: Mapped[str | None] = mapped_column(String(512))
    obligation_type: Mapped[str | None] = mapped_column(String(32))  # payment|delivery|notice|renewal|termination|warranty|claim


class RiskType(str, enum.Enum):
    MISSING_PROTECTION = "missing_protection"
    AMBIGUITY = "ambiguity"
    UNFAIR_ALLOCATION = "unfair_allocation"
    UNLIMITED_LIABILITY = "unlimited_liability"
    ONE_SIDED_TERMINATION = "one_sided_termination"
    PAYMENT_RISK = "payment_risk"
    PENALTY_RISK = "penalty_risk"
    IP_RISK = "ip_risk"
    CONFIDENTIALITY_RISK = "confidentiality_risk"
    DATA_PROTECTION_RISK = "data_protection_risk"
    JURISDICTION_RISK = "jurisdiction_risk"
    DISPUTE_RISK = "dispute_risk"
    RENEWAL_RISK = "renewal_risk"
    ASSIGNMENT_RISK = "assignment_risk"
    CHANGE_OF_CONTROL_RISK = "change_of_control_risk"
    COMPLIANCE_RISK = "compliance_risk"
    OTHER = "other"


class ContractRiskSeverity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RiskCategory(str, enum.Enum):
    """brief §28 — a risk can be commercially bad without being illegal."""

    LEGAL = "legal"
    COMMERCIAL = "commercial"
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    PROCEDURAL = "procedural"
    COMPLIANCE = "compliance"


class RiskClassification(str, enum.Enum):
    """brief §54 — never say "illegal" when only "unfavorable" is supported."""

    ILLEGAL = "illegal"
    UNENFORCEABLE = "unenforceable"
    HIGH_RISK = "high_risk"
    UNFAVORABLE = "unfavorable"
    AMBIGUOUS = "ambiguous"
    MISSING_PROTECTION = "missing_protection"


class RiskVerificationStatus(str, enum.Enum):
    VERIFIED = "verified"
    MOCK = "mock"
    UNVERIFIED = "unverified"


class PartyPerspective(str, enum.Enum):
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    LANDLORD = "landlord"
    TENANT = "tenant"
    EMPLOYER = "employer"
    EMPLOYEE = "employee"
    LICENSOR = "licensor"
    LICENSEE = "licensee"
    NEUTRAL = "neutral"


class AgreementStatus(str, enum.Enum):
    """brief §34 — Analyst vs Reviewer outcome, never silently averaged."""

    AGREED = "agreed"
    DISAGREEMENT = "disagreement"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class ContractRisk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_risks"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"),
        nullable=False)
    clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_clauses.id"))
    risk_type: Mapped[RiskType] = mapped_column(pg_enum(RiskType), nullable=False)
    severity: Mapped[ContractRiskSeverity] = mapped_column(pg_enum(ContractRiskSeverity), nullable=False)
    category: Mapped[RiskCategory] = mapped_column(pg_enum(RiskCategory), nullable=False)
    classification: Mapped[RiskClassification] = mapped_column(pg_enum(RiskClassification), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str | None] = mapped_column(Text)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    party_perspective: Mapped[PartyPerspective] = mapped_column(pg_enum(PartyPerspective), default=PartyPerspective.NEUTRAL)
    confidence: Mapped[str] = mapped_column(String(16), default="low")  # high|medium|low
    verification_status: Mapped[RiskVerificationStatus] = mapped_column(pg_enum(RiskVerificationStatus),
        default=RiskVerificationStatus.UNVERIFIED)
    research_id: Mapped[str | None] = mapped_column(String(64))
    citations: Mapped[dict] = mapped_column(JSONB, default=list)
    agreement_status: Mapped[AgreementStatus] = mapped_column(pg_enum(AgreementStatus), default=AgreementStatus.REQUIRES_HUMAN_REVIEW)
    detector: Mapped[str | None] = mapped_column(String(64))  # which specialized detector raised this


class RecommendationAction(str, enum.Enum):
    KEEP = "keep"
    NEGOTIATE = "negotiate"
    REWRITE = "rewrite"
    REMOVE = "remove"
    ADD = "add"


class ContractRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contract_recommendations"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    risk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_risks.id", ondelete="CASCADE"), nullable=False,
        index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    action: Mapped[RecommendationAction] = mapped_column(pg_enum(RecommendationAction), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    commercial_reason: Mapped[str | None] = mapped_column(Text)


class AlternativeClause(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alternative_clauses"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    original_clause_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_clauses.id", ondelete="CASCADE"),
        nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_text: Mapped[str] = mapped_column(Text, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    risk_reduction: Mapped[str | None] = mapped_column(String(32))  # eliminates|reduces|mitigates
    commercial_tradeoff: Mapped[str | None] = mapped_column(Text)


class RedlineReviewStatus(str, enum.Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RedlineChange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """brief §38-39 — every change is clause-linked, risk-linked, and
    research-linked; there is no such thing as an anonymous redline edit here.
    """

    __tablename__ = "redline_changes"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    clause_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_clauses.id", ondelete="CASCADE"), nullable=False)
    risk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_risks.id"))
    alternative_clause_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("alternative_clauses.id"))
    research_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    diff_ops: Mapped[dict] = mapped_column(JSONB, default=list)  # structured diff — see app/domains/contracts/redline.py
    review_status: Mapped[RedlineReviewStatus] = mapped_column(pg_enum(RedlineReviewStatus), default=RedlineReviewStatus.PROPOSED)


class ReviewDepth(str, enum.Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DETAILED = "detailed"
    FULL_DUE_DILIGENCE = "full_due_diligence"  # extension point — not implemented Phase 4, brief §31


class AnalysisStatus(str, enum.Enum):
    """brief §49 — a contract review is only ever CURRENT relative to the
    Knowledge Base snapshot it was computed against.
    """

    CURRENT = "current"
    STALE = "stale"


class ContractReviewStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ContractReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted contract review run — brief §47 (this is what Phase 3's
    LegalResearchResult deliberately did NOT persist; contract review does,
    since re-running the same analysis for the same version should be
    idempotent — see §48, enforced via `analysis_configuration_hash`).
    """

    __tablename__ = "contract_reviews"

    workspace_id: Mapped[uuid.UUID] = workspace_fk()
    contract_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False,
        index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contract_versions.id", ondelete="CASCADE"),
        nullable=False)
    party_perspective: Mapped[PartyPerspective] = mapped_column(pg_enum(PartyPerspective), default=PartyPerspective.NEUTRAL)
    review_depth: Mapped[ReviewDepth] = mapped_column(pg_enum(ReviewDepth), default=ReviewDepth.STANDARD)
    status: Mapped[ContractReviewStatus] = mapped_column(pg_enum(ContractReviewStatus), default=ContractReviewStatus.RUNNING)
    analysis_status: Mapped[AnalysisStatus] = mapped_column(pg_enum(AnalysisStatus), default=AnalysisStatus.CURRENT)
    analysis_configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    risk_summary: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"critical": 2, "high": 5, ...}
    overall_score: Mapped[int | None] = mapped_column(Integer)  # 0-100, see app/domains/contracts/scoring.py
    performance_ms: Mapped[dict] = mapped_column(JSONB, default=dict)  # brief §58 — clause_extraction_ms/research_ms/total_ms/...
