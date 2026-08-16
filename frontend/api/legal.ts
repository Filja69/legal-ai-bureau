// Typed client for backend/app/api/v1 — one function per LEGAL-API.md resource.
// Endpoints not yet implemented in the backend return HTTP 501; callers should
// surface that as "not available yet", not treat it as an error state.

import { apiClient, withWorkspace } from "@/lib/api-client";
import type { Case, LegalResearchResponse, ResearchMode } from "@/types/legal";

export async function listCases(workspaceId: string): Promise<Case[]> {
  const { data } = await apiClient.get<Case[]>("/api/v1/legal/cases", withWorkspace(workspaceId));
  return data;
}

export async function getCase(workspaceId: string, caseId: string): Promise<Case> {
  const { data } = await apiClient.get<Case>(`/api/v1/legal/cases/${caseId}`, withWorkspace(workspaceId));
  return data;
}

export interface CreateCaseParams {
  title: string;
  clientName?: string;
  counterpartyName?: string;
  matterType?: string;
}

export async function createCase(workspaceId: string, params: CreateCaseParams): Promise<Case> {
  const { data } = await apiClient.post<Case>(
    "/api/v1/legal/cases",
    {
      title: params.title,
      client_name: params.clientName ?? null,
      counterparty_name: params.counterpartyName ?? null,
      matter_type: params.matterType ?? null,
    },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function checkHealth(): Promise<{ status: string }> {
  const { data } = await apiClient.get("/health");
  return data;
}

export interface RunResearchParams {
  workspaceId: string;
  question: string;
  jurisdiction?: string;
  effectiveAt?: string | null;
  facts?: string[];
  requestedOutput?: ResearchMode;
}

export async function runResearch(params: RunResearchParams): Promise<LegalResearchResponse> {
  const { data } = await apiClient.post<LegalResearchResponse>(
    "/api/v1/legal/research",
    {
      question: params.question,
      jurisdiction: params.jurisdiction ?? "RU",
      effective_at: params.effectiveAt ?? null,
      facts: params.facts ?? [],
      requested_output: params.requestedOutput ?? "legal_research",
    },
    withWorkspace(params.workspaceId)
  );
  return data;
}
