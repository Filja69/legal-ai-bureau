// Mirrors backend/app/schemas/litigation.py — Phase 9.3 Litigation & Case Intelligence.

export type PartyType = "individual" | "organization" | "unknown";
export type ProceduralRole = "plaintiff" | "defendant" | "third_party" | "applicant" | "respondent" | "unknown";

export interface CaseParty {
  id: string;
  case_id: string;
  name: string;
  party_type: PartyType;
  procedural_role: ProceduralRole;
  identifiers: Record<string, unknown>;
}

export type CaseDocumentRole =
  | "contract" | "addendum" | "invoice" | "act" | "correspondence" | "claim" | "response"
  | "court_filing" | "court_decision" | "expert_report" | "payment_document" | "other";

export interface CaseDocument {
  id: string;
  case_id: string;
  document_id: string;
  role: CaseDocumentRole;
  document_title: string;
  document_status: string;
}

export type FactType = "date" | "amount" | "party" | "event" | "other";
export type FactStatus = "asserted" | "supported" | "disputed" | "contradicted" | "inferred" | "unknown";

export interface CaseFactEvidence {
  document_id: string;
  document_title: string;
  chunk_id: string | null;
  page_number: number | null;
  section_path: string | null;
  excerpt: string;
}

export interface CaseFact {
  id: string;
  case_id: string;
  statement: string;
  fact_type: FactType;
  status: FactStatus;
  normalized_value: string | null;
  evidence: CaseFactEvidence[];
  created_at: string | null;
}

export type DateType = "exact" | "calculated" | "approximate" | "unknown";

export interface CaseEvent {
  id: string;
  case_id: string;
  event_date: string | null;
  date_type: DateType;
  description: string;
  event_type: string | null;
  source_fact_id: string | null;
}

export type ContradictionType = "date_mismatch" | "amount_mismatch" | "party_mismatch" | "other";

export interface CaseContradiction {
  id: string;
  case_id: string;
  contradiction_type: ContradictionType;
  description: string;
  fact_a_id: string;
  fact_a_statement: string;
  fact_b_id: string;
  fact_b_statement: string;
}

export type EvidenceStrength = "strong" | "moderate" | "weak" | "conflicted" | "insufficient";

export interface EvidenceMatrixRow {
  fact_statement: string;
  fact_type: FactType;
  normalized_value: string;
  strength: EvidenceStrength;
  reasons: string[];
  corroboration_count: number;
}

export interface CaseAnalysisSummary {
  case_id: string;
  fact_count: number;
  contradiction_count: number;
  event_count: number;
}
