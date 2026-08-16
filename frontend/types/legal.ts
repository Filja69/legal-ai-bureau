// Mirrors backend/app/schemas — LEGAL-API.md is the source of truth for shape.

export type CaseStatus = "open" | "research" | "drafting" | "litigation" | "closed";

export interface Case {
  id: string;
  workspace_id: string;
  title: string;
  status: CaseStatus;
  client_name: string | null;
  counterparty_name: string | null;
  matter_type: string | null;
}

export type Confidence = "high" | "medium" | "low";
export type RiskSeverity = "low" | "medium" | "high" | "critical";

export interface LegalIssueRef {
  description: string;
  article_refs: string[];
}

export interface RiskRef {
  severity: RiskSeverity;
  description: string;
  mitigation: string | null;
}

export interface SourceRef {
  citation_id: string | null;
  verification_status: "verified" | "unverified" | "broken";
}

// The structured-output contract every AI-conclusion-bearing endpoint returns —
// see LEGAL-AGENTS.md §7. The frontend renders directly from this shape.
export interface LegalAgentResult {
  conclusion: string;
  confidence: Confidence;
  issues: LegalIssueRef[];
  risks: RiskRef[];
  sources: SourceRef[];
  citations: string[];
  missing_facts: string[];
  recommended_actions: string[];
  escalate_to_human: boolean;
}

// --- Legal Research Engine (Phase 3) — mirrors backend/app/domains/legal_research/models.py ---

export type ClaimVerificationStatus = "verified" | "mock" | "unverified" | "unsupported_critical";
export type ResearchStatus = "completed" | "blocked_unverified_claim" | "research_failed";
export type ResearchMode = "quick_answer" | "legal_research" | "legal_opinion";

export interface ResearchIssue {
  id: string;
  title: string;
  description: string;
  priority: number;
  issue_type: "substantive" | "procedural";
}

export interface ResearchFact {
  subject: string;
  predicate: string;
  object: string | null;
  source: "user_stated" | "source_verified" | "ai_inferred" | "unknown";
  confidence: number;
}

export interface ResearchClaim {
  claim: string;
  claim_type: "rule" | "application" | "conclusion";
  importance: "critical" | "important" | "supporting";
  citations: string[];
  verification_status: ClaimVerificationStatus;
}

export interface ResearchConflict {
  conflict_type: string;
  description: string;
  position_a: string;
  position_b: string;
  implication: string;
}

export interface ResearchMissingFact {
  question: string;
  criticality: "critical" | "important" | "optional";
  reason: string;
}

export interface LegalResearchResult {
  executive_conclusion: string;
  confidence: Confidence;
  issues: ResearchIssue[];
  facts: ResearchFact[];
  claims: ResearchClaim[];
  analysis: string[];
  counterarguments: string[];
  conflicts: ResearchConflict[];
  risks: string[];
  missing_facts: ResearchMissingFact[];
  recommended_actions: string[];
  citations: string[];
  citation_coverage: number;
  escalate_to_human: boolean;
  escalation_reasons: string[];
}

export interface ResearchTrace {
  queries: string[];
  retrieved_count: number;
  llm_calls: number;
  performance_ms: Record<string, number>;
  knowledge_snapshot: { total_chunks: number; mock_chunks: number } | null;
}

export interface LegalResearchResponse {
  research_id: string;
  status: ResearchStatus;
  result: LegalResearchResult;
  trace: ResearchTrace;
}

// --- Phase 8: persisted research reports (GET /research, GET /research/{id}) ---

export interface ResearchReportSummary {
  id: string;
  question: string;
  jurisdiction: string;
  status: ResearchStatus;
  confidence: Confidence;
  executive_conclusion: string;
  escalate_to_human: boolean;
  case_id: string | null;
  created_at: string;
}

export interface ResearchReportList {
  total: number;
  items: ResearchReportSummary[];
}

export interface ResearchReportDetail {
  research_id: string;
  status: ResearchStatus;
  result: LegalResearchResult;
  trace: ResearchTrace;
  created_at: string;
}
