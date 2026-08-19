// Contract Intelligence (Phase 4) — mirrors backend/app/models/contracts.py + app/api/v1/contracts.py.

export type ContractType =
  | "service" | "supply" | "sale" | "lease" | "employment" | "nda" | "license"
  | "loan" | "agency" | "distribution" | "partnership" | "software" | "other" | "unknown";

export type ContractStatus = "draft" | "analyzing" | "analyzed" | "analysis_failed";
export type RiskSeverity = "critical" | "high" | "medium" | "low" | "info";
export type ReviewDepth = "quick" | "standard" | "detailed";
export type PartyPerspective =
  | "customer" | "supplier" | "landlord" | "tenant" | "employer" | "employee" | "licensor" | "licensee" | "neutral";

export interface Contract {
  id: string;
  workspace_id: string;
  title: string;
  contract_type: ContractType;
  status: ContractStatus;
  is_mock: boolean;
}

// Mirrors backend/app/schemas/contract.py ContractCreate — exactly one of
// raw_text/document_id is meaningful; document_id takes precedence on the
// backend if both are somehow set, so callers should only ever send one.
export interface ContractCreateInput {
  title: string;
  contract_type: ContractType;
  raw_text?: string;
  document_id?: string;
}

export interface ContractClause {
  id: string;
  clause_number: string | null;
  clause_type: string;
  original_text: string;
  position_start: number;
  position_end: number;
  confidence: number;
}

export interface ContractRisk {
  id: string;
  clause_id: string | null;
  risk_type: string;
  severity: RiskSeverity;
  category: string;
  classification: string;
  title: string;
  description: string;
  why_it_matters: string | null;
  legal_basis: string | null;
  confidence: string;
  verification_status: "verified" | "mock" | "unverified";
  citations: string[];
  agreement_status: "agreed" | "disagreement" | "requires_human_review";
}

export interface AnalyzeResponse {
  review_id: string;
  status: string;
  overall_score: number;
  risk_summary: Record<RiskSeverity, number>;
  executive_summary: string;
  analysis_status: "current" | "stale";
}

export interface ContractReportRisk extends Omit<ContractRisk, "agreement_status"> {
  recommendation: { action: string; reason: string } | null;
  alternative_clause: { proposed_text: string; change_reason: string } | null;
}

export interface ContractReport {
  contract_id: string;
  contract_type: ContractType;
  executive_summary: string;
  overall_score: number;
  risk_summary: Record<RiskSeverity, number>;
  risks: ContractReportRisk[];
  performance_ms: Record<string, number>;
  knowledge_snapshot: { total_chunks: number; mock_chunks: number };
  analysis_status: "current" | "stale";
}

export type RedlineReviewStatus = "proposed" | "accepted" | "rejected";

export interface DiffOp {
  op: "equal" | "insert" | "delete";
  text: string;
}

export interface RedlineChange {
  id: string;
  clause_id: string;
  risk_id: string | null;
  research_id: string | null;
  reason: string;
  diff_ops: DiffOp[];
  review_status: RedlineReviewStatus;
}

export interface ContractVersion {
  id: string;
  version_number: number;
  is_current: boolean;
  content_hash: string;
  created_at: string;
}
