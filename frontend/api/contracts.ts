// Typed client for /contracts — LEGAL-API.md §Contract Intelligence (Phase 4).

import { apiClient, withWorkspace } from "@/lib/api-client";
import type {
  AnalyzeResponse,
  Contract,
  ContractClause,
  ContractReport,
  ContractRisk,
  ContractType,
  ContractVersion,
  PartyPerspective,
  RedlineChange,
  RedlineReviewStatus,
  ReviewDepth,
} from "@/types/contract";

export async function listContracts(workspaceId: string): Promise<Contract[]> {
  const { data } = await apiClient.get<Contract[]>("/api/v1/legal/contracts", withWorkspace(workspaceId));
  return data;
}

export async function getContract(workspaceId: string, contractId: string): Promise<Contract> {
  const { data } = await apiClient.get<Contract>(`/api/v1/legal/contracts/${contractId}`, withWorkspace(workspaceId));
  return data;
}

export async function createContract(
  workspaceId: string,
  title: string,
  rawText: string,
  contractType: ContractType = "unknown"
): Promise<Contract> {
  const { data } = await apiClient.post<Contract>(
    "/api/v1/legal/contracts",
    { title, raw_text: rawText, contract_type: contractType },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function analyzeContract(
  workspaceId: string,
  contractId: string,
  options?: { partyPerspective?: PartyPerspective; reviewDepth?: ReviewDepth; force?: boolean }
): Promise<AnalyzeResponse> {
  const { data } = await apiClient.post<AnalyzeResponse>(
    `/api/v1/legal/contracts/${contractId}/analyze`,
    {
      party_perspective: options?.partyPerspective ?? "neutral",
      review_depth: options?.reviewDepth ?? "standard",
      force: options?.force ?? false,
    },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function getContractClauses(workspaceId: string, contractId: string): Promise<ContractClause[]> {
  const { data } = await apiClient.get<ContractClause[]>(`/api/v1/legal/contracts/${contractId}/clauses`, withWorkspace(workspaceId));
  return data;
}

export async function getContractRisks(workspaceId: string, contractId: string): Promise<ContractRisk[]> {
  const { data } = await apiClient.get<ContractRisk[]>(`/api/v1/legal/contracts/${contractId}/risks`, withWorkspace(workspaceId));
  return data;
}

export async function getContractReport(workspaceId: string, contractId: string): Promise<ContractReport> {
  const { data } = await apiClient.get<ContractReport>(`/api/v1/legal/contracts/${contractId}/report`, withWorkspace(workspaceId));
  return data;
}

export async function getRedline(workspaceId: string, contractId: string): Promise<RedlineChange[]> {
  const { data } = await apiClient.post<RedlineChange[]>(`/api/v1/legal/contracts/${contractId}/redline`, {}, withWorkspace(workspaceId));
  return data;
}

export async function decideRedlineChange(
  workspaceId: string,
  contractId: string,
  changeId: string,
  decision: Exclude<RedlineReviewStatus, "proposed">
): Promise<RedlineChange> {
  const { data } = await apiClient.patch<RedlineChange>(
    `/api/v1/legal/contracts/${contractId}/redline/${changeId}`,
    { decision },
    withWorkspace(workspaceId)
  );
  return data;
}

export async function listContractVersions(workspaceId: string, contractId: string): Promise<ContractVersion[]> {
  const { data } = await apiClient.get<ContractVersion[]>(`/api/v1/legal/contracts/${contractId}/versions`, withWorkspace(workspaceId));
  return data;
}
