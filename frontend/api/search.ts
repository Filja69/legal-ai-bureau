// Typed client for /search/global — LEGAL-API.md §Search (Phase 8).

import { apiClient, withWorkspace } from "@/lib/api-client";

export type GlobalSearchResultType = "CASE" | "CONTRACT" | "DOCUMENT" | "RESEARCH" | "LAW";

export interface GlobalSearchResult {
  type: GlobalSearchResultType;
  id: string;
  title: string;
  subtitle: string | null;
}

export interface GlobalSearchResponse {
  query: string;
  results: GlobalSearchResult[];
}

export async function searchGlobal(workspaceId: string, query: string): Promise<GlobalSearchResponse> {
  const config = withWorkspace(workspaceId);
  const { data } = await apiClient.get<GlobalSearchResponse>("/api/v1/legal/search/global", {
    ...config,
    params: { q: query },
  });
  return data;
}
