"""Legal Research Engine — structured data model (Phase 3 brief §3-8, §12-14,
§24-27, §31-32, §36, §39, §44).

This module is data only, no behavior — every stage of the engine
(app/domains/legal_research/*.py) imports from here rather than each
inventing its own shape. Keeping the model in one file makes it easy to see
the whole pipeline's data contract at a glance.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

# --- Request ---


class ResearchMode(str, enum.Enum):
    QUICK_ANSWER = "quick_answer"
    LEGAL_RESEARCH = "legal_research"
    LEGAL_OPINION = "legal_opinion"
    CASE_ANALYSIS = "case_analysis"  # extension point — not implemented Phase 3, brief §39
    SECOND_OPINION = "second_opinion"  # extension point — not implemented Phase 3, brief §39


_IMPLEMENTED_MODES = {ResearchMode.QUICK_ANSWER, ResearchMode.LEGAL_RESEARCH, ResearchMode.LEGAL_OPINION}


@dataclass
class LegalResearchRequest:
    question: str
    jurisdiction: str = "RU"
    effective_at: date | None = None
    case_context: str | None = None
    facts: list[str] = field(default_factory=list)
    requested_output: ResearchMode = ResearchMode.LEGAL_RESEARCH


# --- Facts ---


class FactOrigin(str, enum.Enum):
    USER_STATED = "user_stated"
    SOURCE_VERIFIED = "source_verified"
    AI_INFERRED = "ai_inferred"
    UNKNOWN = "unknown"


@dataclass
class LegalFact:
    subject: str
    predicate: str
    object: str | None = None
    date: date | None = None
    source: FactOrigin = FactOrigin.USER_STATED
    confidence: float = 1.0


class Criticality(str, enum.Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


@dataclass
class MissingFact:
    question: str
    criticality: Criticality
    reason: str = ""


# --- Issues ---


class IssueType(str, enum.Enum):
    """Brief §30 — whether a right exists (substantive) is a different
    question from whether it can currently be procedurally exercised.
    """

    SUBSTANTIVE = "substantive"
    PROCEDURAL = "procedural"


@dataclass
class LegalIssue:
    id: str
    title: str
    description: str
    priority: int  # 1 = primary issue, 2+ = secondary, lower is more important
    parent_issue: str | None = None
    issue_type: IssueType = IssueType.SUBSTANTIVE


@dataclass
class ResearchPlan:
    issues: list[LegalIssue]
    date_constraint: date | None = None
    legal_domains: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)


# --- Queries ---


class QueryType(str, enum.Enum):
    LAW = "law"
    COURT_PRACTICE = "court_practice"
    LEGAL_POSITION = "legal_position"
    COUNTERARGUMENT = "counterargument"
    DEFINITION = "definition"
    PROCEDURAL = "procedural"


@dataclass
class ResearchQuery:
    text: str
    query_type: QueryType
    issue_id: str | None = None


# --- Evidence ---


class AuthorityLevel(str, enum.Enum):
    """Internal ranking signal only — brief §14 is explicit this is NOT a
    statement of legal force in the formal/constitutional sense.
    """

    CONSTITUTIONAL = "constitutional"
    FEDERAL_LAW = "federal_law"
    CODE = "code"
    PRESIDENTIAL_ACT = "presidential_act"
    GOVERNMENT_ACT = "government_act"
    MINISTERIAL_ACT = "ministerial_act"
    SUPREME_COURT = "supreme_court"
    CASSATION = "cassation"
    APPEAL = "appeal"
    FIRST_INSTANCE = "first_instance"
    OFFICIAL_EXPLANATION = "official_explanation"
    SECONDARY_SOURCE = "secondary_source"
    MOCK = "mock"


# Higher = more authoritative. Used only to break ties / weight ranking,
# never surfaced to a user as "legal force" (brief §14).
AUTHORITY_RANK: dict[AuthorityLevel, int] = {
    AuthorityLevel.CONSTITUTIONAL: 13,
    AuthorityLevel.FEDERAL_LAW: 12,
    AuthorityLevel.CODE: 11,
    AuthorityLevel.PRESIDENTIAL_ACT: 10,
    AuthorityLevel.GOVERNMENT_ACT: 9,
    AuthorityLevel.MINISTERIAL_ACT: 8,
    AuthorityLevel.SUPREME_COURT: 7,
    AuthorityLevel.CASSATION: 6,
    AuthorityLevel.APPEAL: 5,
    AuthorityLevel.FIRST_INSTANCE: 4,
    AuthorityLevel.OFFICIAL_EXPLANATION: 3,
    AuthorityLevel.SECONDARY_SOURCE: 2,
    AuthorityLevel.MOCK: 1,
}


@dataclass
class EvidenceItem:
    source: str
    citation: str
    text: str
    retrieval_score: float
    retrieval_method: list[str]
    authority: AuthorityLevel | None = None  # filled by EvidenceRanker
    relevance: float = 0.0  # composite ranking score, filled by EvidenceRanker
    effective_at: str | None = None
    verification_status: str = "unverified"
    chunk_id: str | None = None
    document_id: str | None = None  # dedup/diversity key: law_id or court_decision_id
    is_mock: bool = False
    issue_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class EvidencePool:
    items: list[EvidenceItem] = field(default_factory=list)

    @property
    def unique_documents(self) -> set[str]:
        return {i.document_id for i in self.items if i.document_id}

    @property
    def unique_authorities(self) -> set[AuthorityLevel]:
        return {i.authority for i in self.items if i.authority is not None}


# --- Claims ---


class ClaimImportance(str, enum.Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    SUPPORTING = "supporting"


class ClaimVerificationStatus(str, enum.Enum):
    VERIFIED = "verified"
    MOCK = "mock"
    UNVERIFIED = "unverified"
    UNSUPPORTED_CRITICAL = "unsupported_critical"  # brief §25 — blocks finalization


@dataclass
class LegalClaim:
    claim: str
    claim_type: str  # "rule" | "application" | "conclusion"
    importance: ClaimImportance
    citations: list[str] = field(default_factory=list)
    verification_status: ClaimVerificationStatus = ClaimVerificationStatus.UNVERIFIED
    issue_id: str | None = None


# --- Conflicts ---


class ConflictType(str, enum.Enum):
    STATUTORY_CONFLICT = "statutory_conflict"
    TEMPORAL_CONFLICT = "temporal_conflict"
    JURISPRUDENTIAL_CONFLICT = "jurisprudential_conflict"
    FACTUAL_CONFLICT = "factual_conflict"
    INTERPRETATION_CONFLICT = "interpretation_conflict"


@dataclass
class LegalConflict:
    conflict_type: ConflictType
    description: str
    position_a: str
    position_b: str
    later_position: str | None = None
    supreme_court_position: str | None = None
    implication: str = ""


# --- Confidence ---


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- Review ---


@dataclass
class ReviewFindings:
    """LegalResearchReviewer output — LEGAL-AGENTS.md §5 two-lawyer principle
    applied to research, brief §22. Deterministic checks, not LLM prose.
    """

    all_critical_facts_addressed: bool
    issues_look_complete: bool
    unsupported_critical_claims: list[str]
    has_conflicting_practice: bool
    outdated_redaction_used: bool
    conclusion_overreaches: bool
    notes: list[str] = field(default_factory=list)


# --- Result & Trace ---


@dataclass
class CaseLawRelevance:
    """Whether a citation-VALIDATED court decision (existence and provenance
    already confirmed by CitationValidator) actually bears on the question —
    keyword retrieval and authority ranking alone don't answer that. See
    case_law_relevance.py for how this gets filled in; never itself a new
    citation, only a characterization of one already established as real.
    """

    case_number: str
    court_level_label: str
    decision_date: str | None
    outcome: str | None
    factual_similarity: str  # "high" | "medium" | "low" | "unassessed"
    legal_issue_similarity: str
    procedural_posture_note: str
    stance: str  # "supports" | "against" | "distinguishable" | "unclear" | "unassessed"
    distinguishing_facts: list[str] = field(default_factory=list)
    remains_useful: bool = True
    assessed: bool = True


@dataclass
class LegalResearchResult:
    executive_conclusion: str
    confidence: ConfidenceLevel
    issues: list[LegalIssue] = field(default_factory=list)
    facts: list[LegalFact] = field(default_factory=list)
    claims: list[LegalClaim] = field(default_factory=list)
    analysis: list[str] = field(default_factory=list)  # IRAC "Application" narratives, one per issue
    counterarguments: list[str] = field(default_factory=list)
    conflicts: list[LegalConflict] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    missing_facts: list[MissingFact] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    citation_coverage: float = 0.0
    escalate_to_human: bool = False
    escalation_reasons: list[str] = field(default_factory=list)
    status: str = "completed"  # "completed" | "research_failed" | "blocked_unverified_claim"
    case_law_relevance: list[CaseLawRelevance] = field(default_factory=list)


@dataclass
class KnowledgeSnapshot:
    """What state of the Knowledge Base a research result was computed
    against — brief §44, needed so a later KB update can mark old research
    STALE (persistence itself is Phase 4+, see LEGAL-ROADMAP.md; this is the
    in-memory shape captured into the trace today).
    """

    total_chunks: int
    mock_chunks: int
    captured_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ResearchTrace:
    """Audit trail — brief §36-37: structured summary only, NEVER the model's
    private chain-of-thought. Every field here is either a count, an id, or
    already-public structured data (queries actually run, sources actually
    retrieved) — nothing here is a hidden reasoning transcript.
    """

    research_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    question: str = ""
    facts_count: int = 0
    issues: list[str] = field(default_factory=list)  # issue titles
    queries: list[str] = field(default_factory=list)  # query texts actually run
    retrieved_count: int = 0
    filtered_count: int = 0  # after verification/authority/diversity filtering
    counterarguments_found: int = 0
    conflicts_found: int = 0
    review_notes: list[str] = field(default_factory=list)
    knowledge_snapshot: KnowledgeSnapshot | None = None
    performance_ms: dict[str, float] = field(default_factory=dict)
    llm_calls: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
