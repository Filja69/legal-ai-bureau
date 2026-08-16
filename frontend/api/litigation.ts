// Typed client for Case Intelligence — LEGAL-API.md §Cases, Phase 9.3.

import { apiClient, withWorkspace } from "@/lib/api-client";
import type {
  CaseAnalysisSummary,
  CaseContradiction,
  CaseDocument,
  CaseDocumentRole,
  CaseEvent,
  CaseFact,
  CaseParty,
  EvidenceMatrixRow,
  PartyType,
  ProceduralRole,
} from "@/types/litigation";

export async function listCaseParties(workspaceId: string, caseId: string): Promise<CaseParty[]> {
  const { data } = await apiClient.get<CaseParty[]>(`/api/v1/legal/cases/${caseId}/parties`, withWorkspace(workspaceId));
  return data;
}

export async function addCaseParty(
  workspaceId: string,
  caseId: string,
  params: { name: string; partyType: PartyType; proceduralRole: ProceduralRole }
): Promise<CaseParty> {
  const { data } = await apiClient.post<CaseParty>(
    `/api/v1/legal/cases/${caseId}/parties`,
    { name: params.name, party_type: params.partyType, procedural_role: params.proceduralRole },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function listCaseDocuments(workspaceId: string, caseId: string): Promise<CaseDocument[]> {
  const { data } = await apiClient.get<CaseDocument[]>(`/api/v1/legal/cases/${caseId}/documents`, withWorkspace(workspaceId));
  return data;
}

export async function attachCaseDocument(
  workspaceId: string,
  caseId: string,
  documentId: string,
  role: CaseDocumentRole = "other"
): Promise<CaseDocument> {
  const { data } = await apiClient.post<CaseDocument>(
    `/api/v1/legal/cases/${caseId}/documents`,
    { document_id: documentId, role },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function listCaseFacts(workspaceId: string, caseId: string): Promise<CaseFact[]> {
  const { data } = await apiClient.get<CaseFact[]>(`/api/v1/legal/cases/${caseId}/facts`, withWorkspace(workspaceId));
  return data;
}

export async function extractCaseFacts(workspaceId: string, caseId: string): Promise<CaseFact[]> {
  const { data } = await apiClient.post<CaseFact[]>(`/api/v1/legal/cases/${caseId}/facts/extract`, {}, withWorkspace(workspaceId));
  return data;
}

export async function getCaseTimeline(workspaceId: string, caseId: string): Promise<CaseEvent[]> {
  const { data } = await apiClient.get<CaseEvent[]>(`/api/v1/legal/cases/${caseId}/timeline`, withWorkspace(workspaceId));
  return data;
}

export async function buildCaseTimeline(workspaceId: string, caseId: string): Promise<CaseEvent[]> {
  const { data } = await apiClient.post<CaseEvent[]>(`/api/v1/legal/cases/${caseId}/timeline/build`, {}, withWorkspace(workspaceId));
  return data;
}

export async function listCaseContradictions(workspaceId: string, caseId: string): Promise<CaseContradiction[]> {
  const { data } = await apiClient.get<CaseContradiction[]>(`/api/v1/legal/cases/${caseId}/contradictions`, withWorkspace(workspaceId));
  return data;
}

export async function getCaseEvidenceMatrix(workspaceId: string, caseId: string): Promise<EvidenceMatrixRow[]> {
  const { data } = await apiClient.get<EvidenceMatrixRow[]>(`/api/v1/legal/cases/${caseId}/evidence-matrix`, withWorkspace(workspaceId));
  return data;
}

export async function analyzeCase(workspaceId: string, caseId: string): Promise<CaseAnalysisSummary> {
  const { data } = await apiClient.post<CaseAnalysisSummary>(`/api/v1/legal/cases/${caseId}/analyze`, {}, withWorkspace(workspaceId));
  return data;
}
