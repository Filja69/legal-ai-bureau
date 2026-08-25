"use client";

import { useQuery } from "@tanstack/react-query";
import { getResearchReport } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import { ResearchResult } from "./ResearchResult";

export function ResearchDetailView({ reportId }: { reportId: string }) {
  const { workspaceId } = useAuth();

  const reportQuery = useQuery({
    queryKey: ["research", "detail", workspaceId, reportId],
    queryFn: () => getResearchReport(workspaceId!, reportId),
    enabled: !!workspaceId,
    retry: false,
  });

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Select a workspace to view this research report.</div>;
  }

  if (reportQuery.isLoading) {
    return <div className="p-8 text-sm text-muted">Loading…</div>;
  }

  if (reportQuery.isError) {
    return <div className="p-8 text-sm text-danger">Research report not found.</div>;
  }

  if (!reportQuery.data) return null;

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-ink">Research Report</h1>
        <span className="text-xs text-muted">{new Date(reportQuery.data.created_at).toLocaleString()}</span>
      </div>
      <div className="mt-6">
        <ResearchResult status={reportQuery.data.status} result={reportQuery.data.result} trace={reportQuery.data.trace} />
      </div>
    </div>
  );
}
