// Typed client for persisted research reports — LEGAL-API.md §Legal Research (Phase 8).

import { apiClient, withWorkspace } from "@/lib/api-client";
import type { ResearchReportDetail, ResearchReportList } from "@/types/legal";

export async function listResearchReports(
  workspaceId: string,
  options?: { caseId?: string; limit?: number; offset?: number }
): Promise<ResearchReportList> {
  const config = withWorkspace(workspaceId);
  const { data } = await apiClient.get<ResearchReportList>("/api/v1/legal/research", {
    ...config,
    params: {
      ...(options?.caseId ? { case_id: options.caseId } : {}),
      ...(options?.limit ? { limit: options.limit } : {}),
      ...(options?.offset ? { offset: options.offset } : {}),
    },
  });
  return data;
}

export async function getResearchReport(workspaceId: string, reportId: string): Promise<ResearchReportDetail> {
  const { data } = await apiClient.get<ResearchReportDetail>(
    `/api/v1/legal/research/${reportId}`,
    withWorkspace(workspaceId)
  );
  return data;
}
