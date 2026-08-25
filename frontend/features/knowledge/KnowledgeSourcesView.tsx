"use client";

import axios from "axios";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listKnowledgeSources, syncKnowledgeSource } from "@/api/knowledge";
import { Badge, Card, Notice, PageHeader } from "@/components/ui";
import { KnowledgeNav } from "./KnowledgeNav";

export function KnowledgeSourcesView() {
  const queryClient = useQueryClient();
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const sourcesQuery = useQuery({ queryKey: ["knowledge", "sources"], queryFn: listKnowledgeSources, retry: false });
  const isForbidden = axios.isAxiosError(sourcesQuery.error) && sourcesQuery.error.response?.status === 403;

  async function handleSync(sourceId: string) {
    setSyncingId(sourceId);
    setSyncError(null);
    try {
      await syncKnowledgeSource(sourceId);
      await queryClient.invalidateQueries({ queryKey: ["knowledge", "sources"] });
    } catch (err) {
      const message = axios.isAxiosError(err) ? (err.response?.data?.detail ?? "Sync failed.") : "Sync failed.";
      setSyncError(message);
    } finally {
      setSyncingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader title="Knowledge Base" />
      <div className="mb-6">
        <KnowledgeNav />
      </div>

      {sourcesQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {isForbidden && <Notice tone="danger">Admin or Owner role required to view sources.</Notice>}
      {sourcesQuery.isError && !isForbidden && <Notice tone="danger">Could not load sources.</Notice>}
      {sourcesQuery.data?.length === 0 && <p className="text-sm text-muted">No sources configured.</p>}
      {syncError && (
        <div className="mb-3">
          <Notice tone="danger">{syncError}</Notice>
        </div>
      )}

      <div className="space-y-2.5">
        {sourcesQuery.data?.map((s) => (
          <Card key={s.id}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-medium text-ink">{s.name}</span>
                {s.is_mock && <Badge tone="amber">MOCK</Badge>}
                {s.is_official && <Badge tone="green">OFFICIAL</Badge>}
              </div>
              <button
                onClick={() => handleSync(s.id)}
                disabled={syncingId === s.id}
                className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-panel-muted disabled:opacity-50"
              >
                {syncingId === s.id ? "Syncing…" : "Sync"}
              </button>
            </div>
            <div className="mt-1.5 text-xs text-muted">
              {s.type} · {s.status}
              {s.last_successful_sync_at && ` · last synced ${s.last_successful_sync_at}`}
            </div>
            {s.last_error && <div className="mt-1 text-xs text-danger">{s.last_error}</div>}
          </Card>
        ))}
      </div>
    </div>
  );
}
