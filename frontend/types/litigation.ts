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

// --- Case Result Summary (client-facing) ---

export interface MoneyFlowTransaction {
  payment_order_id: string;
  document_id: string;
  payment_date: string | null;
  amount: string | null;
  payer: string | null;
  recipient: string | null;
  referenced_contract_date: string | null;
}

export interface MoneyFlow {
  transaction_count: number;
  transactions: MoneyFlowTransaction[];
  total_amount: string;
  referenced_contract_dates: Record<string, number>;
  referenced_contract_numbers: Record<string, number>;
}

export interface CaseSnapshot {
  party_names: string[];
  document_count: number;
  payment_count: number;
  total_amount: string;
  key_dates: [string | null, string][];
}

export interface KeyFinding {
  severity: string;
  statement: string;
  source_document_id: string;
  source_document_title: string;
  page_number: number | null;
  excerpt: string;
  confidence: string;
  caveat: string | null;
}

export interface MissingEvidenceItem {
  priority: string;
  description: string;
  why_it_matters: string;
  source_document_id: string | null;
  source_document_title: string | null;
}

export interface NextBestAction {
  priority: number;
  action: string;
  why: string;
}

export type RelationshipType = "director" | "shareholder" | "member" | "other";
export type RelationshipVerificationStatus = "unverified" | "document_supported" | "externally_verified" | "conflicting";

export interface PartyRelationshipFinding {
  subject_name: string;
  related_party_name: string;
  relationship_type: RelationshipType;
  relationship_start: string | null;
  relationship_end: string | null;
  timing_note: string;
  why_it_may_matter: string;
  what_is_still_needed: string[];
  verification_status: RelationshipVerificationStatus;
  source_document_id: string | null;
  source_document_title: string | null;
  source_excerpt: string | null;
}

export interface CaseResultSummary {
  case_snapshot: CaseSnapshot;
  key_findings: KeyFinding[];
  money_flow: MoneyFlow;
  what_this_may_mean: string[];
  missing_critical_evidence: MissingEvidenceItem[];
  next_best_actions: NextBestAction[];
  legal_kb_warning: string | null;
  party_relationship_findings: PartyRelationshipFinding[];
}

// --- Case Intelligence: party relationships, hypothesis register, related litigation ---

export type HypothesisCategory = "fact" | "counsel_hypothesis" | "ai_inference" | "missing_evidence";

export interface CasePartyRelationship {
  id: string;
  case_id: string;
  subject_party_id: string;
  related_party_id: string;
  relationship_type: RelationshipType;
  ownership_percentage: string | null;
  start_date: string | null;
  end_date: string | null;
  source_document_id: string | null;
  source_excerpt: string | null;
  verification_status: RelationshipVerificationStatus;
  notes: string | null;
}

export interface CaseHypothesis {
  id: string;
  case_id: string;
  category: HypothesisCategory;
  statement: string;
  required_verification: string[];
  related_relationship_id: string | null;
  source: string | null;
}

export interface CaseRelatedLitigation {
  id: string;
  case_id: string;
  court: string | null;
  case_number: string | null;
  parties_description: string | null;
  subject_matter: string | null;
  amount_in_dispute: string | null;
  status: string | null;
  note: string | null;
  contextual_note: string;
}

// --- Master Case Report ---

export type FindingCategory =
  | "claim_contradiction" | "payment_pattern" | "contract_formation" | "contract_mismatch" | "course_of_dealing"
  | "party_conduct" | "interest_calculation" | "procedural" | "corporate_relationship" | "related_litigation"
  | "evidence_gap" | "legal_argument" | "risk" | "other";

export interface MasterFinding {
  id: string;
  category: FindingCategory;
  title: string;
  statement: string;
  supporting_facts: string[];
  contradicting_facts: string[];
  source_document_ids: string[];
  source_document_titles: string[];
  excerpts: string[];
  page_numbers: (number | null)[];
  helps_side: string;
  hurts_side: string;
  strength: string;
  confidence: string;
  legal_significance: string;
  counterargument: string | null;
  response_to_counterargument: string | null;
  caveat: string | null;
  missing_evidence: string[];
  recommended_action: string | null;
  verification_status: string;
  alternative_explanations: string[];
  what_would_strengthen: string[];
  what_would_weaken: string[];
  legal_research_required: boolean;
}

export interface CaseOnePager {
  case_position: string;
  strongest_point: string | null;
  biggest_risk: string | null;
  money_at_stake: string;
  top_arguments: string[];
  top_risks: string[];
  what_opponent_must_explain: string[];
  what_court_likely_focuses_on: string | null;
  missing_p0_evidence: string[];
  next_best_action: string | null;
}

export interface CourtScenario {
  scenario: string;
  why_court_could_get_there: string;
  facts_supporting: string[];
  facts_against: string[];
  label: string;
}

export interface DraftResponseSection {
  section: string;
  argument: string;
  supporting_finding_ids: string[];
  caution: string | null;
}

export interface BurdenItem {
  proposition: string;
  side: string;
  current_evidence: string[];
  contrary_evidence: string[];
  status: string;
  weakness: string | null;
  how_to_attack: string | null;
}

export interface CaseMap {
  claimed_amounts: string[];
  claim_dates: string[];
  note: string;
}

export interface ContractVersionTerms {
  document_id: string;
  document_title: string;
  amounts: string[];
  interest_rate: string | null;
  maturity_dates: string[];
  formation_clause_present: boolean;
  signature_status: string;
}

export interface MasterCaseReport {
  one_pager: CaseOnePager;
  case_map: CaseMap;
  findings: MasterFinding[];
  burden_map: BurdenItem[];
  court_scenarios: CourtScenario[];
  opposing_party_questions: string[];
  draft_response_structure: DraftResponseSection[];
  contract_version_matrix: ContractVersionTerms[];
  money_flow: MoneyFlow;
  legal_kb_warning: string | null;
}
