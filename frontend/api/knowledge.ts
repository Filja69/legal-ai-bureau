// Typed client for the /knowledge/* admin namespace — LEGAL-API.md §Knowledge base.
// Admin/Owner only on the backend (require_role); the frontend must not build
// a second debug engine, only call these existing endpoints (Phase 8 brief §17).

import { apiClient } from "@/lib/api-client";

export interface KnowledgeSource {
  id: string;
  name: string;
  type: string;
  is_official: boolean;
  is_mock: boolean;
  status: string;
  last_sync_at: string | null;
  last_successful_sync_at: string | null;
  last_error: string | null;
}

export async function listKnowledgeSources(): Promise<KnowledgeSource[]> {
  const { data } = await apiClient.get<KnowledgeSource[]>("/api/v1/legal/knowledge/sources");
  return data;
}

export async function syncKnowledgeSource(sourceId: string): Promise<{ source_id: string; ingested: number; skipped: number }> {
  const { data } = await apiClient.post(`/api/v1/legal/knowledge/sources/${sourceId}/sync`);
  return data;
}

export interface IndexStatus {
  total_chunks: number;
  by_document_type: Record<string, number>;
  mock_chunks: number;
  embedding_chunks: number;
  pending_embeddings: number;
  failed_embeddings: number;
  active_embedding: {
    provider: string;
    model: string;
    dimensions: number;
    namespace: string;
    chunks_in_active_namespace: number;
  };
  by_namespace: Record<string, number>;
}

export async function getIndexStatus(): Promise<IndexStatus> {
  const { data } = await apiClient.get<IndexStatus>("/api/v1/legal/knowledge/index-status");
  return data;
}

export interface KnowledgeDocument {
  chunk_id: string;
  chunk_type: string;
  document_type: string;
  article_number: string | null;
  is_mock: boolean;
  embedding_model: string;
}

export async function listKnowledgeDocuments(limit = 50): Promise<KnowledgeDocument[]> {
  const { data } = await apiClient.get<KnowledgeDocument[]>("/api/v1/legal/knowledge/documents", { params: { limit } });
  return data;
}

export interface ReindexReport {
  target_namespace: string;
  total: number;
  reindexed: number;
  already_current: number;
  would_reindex: number;
  failed: number;
  errors: string[];
  dry_run: boolean;
  ready_to_activate: boolean;
}

export async function reindexKnowledgeBase(dryRun: boolean): Promise<ReindexReport> {
  const { data } = await apiClient.post<ReindexReport>("/api/v1/legal/knowledge/reindex", { dry_run: dryRun });
  return data;
}

export interface SearchDebugResult {
  query: string;
  effective_at: string | null;
  keyword_results: unknown[];
  vector_results: unknown[];
  hybrid_results: { document_id: string; title: string; score: number; retrieval_mode: string; metadata: Record<string, unknown> }[];
  fusion: { method: string; candidate_count: number };
  filters: { jurisdiction: string; top_k: number };
  embedding: { provider: string; model: string; namespace: string };
  latency_ms: Record<string, number>;
  citation_validation: { document_id: string; law_short_name: string; article_number: string; status: string }[];
}

export async function searchDebug(query: string, jurisdiction = "RU", topK = 10): Promise<SearchDebugResult> {
  const { data } = await apiClient.post<SearchDebugResult>("/api/v1/legal/search/debug", {
    query,
    jurisdiction,
    top_k: topK,
  });
  return data;
}
