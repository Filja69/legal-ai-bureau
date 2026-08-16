// Mirrors backend/app/schemas/document.py — Phase 9.2 real pipeline fields.

export type DocumentType = "contract" | "evidence" | "correspondence" | "generated" | "other";

export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed" | "ocr_required" | "unsupported";

export interface Document {
  id: string;
  workspace_id: string;
  title: string;
  document_type: DocumentType;
  original_filename: string | null;
  media_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  status: DocumentStatus;
  processing_error: string | null;
  created_at: string | null;
  processed_at: string | null;
  doc_metadata: {
    extractor?: string;
    page_count?: number;
    chunk_count?: number;
    used_structure_detection?: boolean;
    warnings?: string[];
  };
}

export interface DocumentCitation {
  citation_type: string;
  document_id: string;
  document_title: string;
  page_number: number | null;
  section_path: string | null;
  excerpt: string;
  label: string;
  chunk_id: string | null;
  content_hash: string | null;
}

export interface DocumentAskResponse {
  status: "answered" | "insufficient_document_evidence";
  answer: string;
  citations: DocumentCitation[];
  // "extractive" = deterministic regex match, no LLM call; "llm" = evidence-gated LLM reasoning.
  answer_method: "extractive" | "llm";
}

export interface ExtractedFact {
  value: string;
  provenance: string;
  kind: "date" | "amount" | "party";
}

export interface DocumentAnalyzeResponse {
  status: "analyzed" | "insufficient_document_evidence";
  document_type_extracted: string | null;
  extracted_dates: ExtractedFact[];
  extracted_amounts: ExtractedFact[];
  extracted_parties: ExtractedFact[];
  inferred_obligations: string[];
  inferred_risks: string[];
  inferred_missing_information: string[];
}
