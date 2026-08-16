"use client";

import axios from "axios";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listKnowledgeSources, syncKnowledgeSource } from "@/api/knowledge";
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
      const message = axios.isAxiosError(err) ? err.response?.data?.detail ?? "Sync failed." : "Sync failed.";
      setSyncError(message);
    } finally {
      setSyncingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Knowledge Base</h1>
      <div className="mt-4">
        <KnowledgeNav />
      </div>

      <div className="mt-6">
        {sourcesQuery.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
        {isForbidden && <p className="text-sm text-red-400">Admin or Owner role required to view sources.</p>}
        {sourcesQuery.isError && !isForbidden && <p className="text-sm text-red-400">Could not load sources.</p>}
        {sourcesQuery.data?.length === 0 && <p className="text-sm text-slate-500">No sources configured.</p>}
        {syncError && <p className="mb-3 text-sm text-red-400">{syncError}</p>}

        <ul className="space-y-2">
          {sourcesQuery.data?.map((s) => (
            <li key={s.id} className="rounded border border-slate-800 p-3 text-sm">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-medium text-slate-200">{s.name}</span>
                  {s.is_mock && <span className="ml-2 rounded bg-amber-900 px-1.5 py-0.5 text-[10px] text-amber-300">MOCK</span>}
                  {s.is_official && <span className="ml-2 rounded bg-emerald-900 px-1.5 py-0.5 text-[10px] text-emerald-300">OFFICIAL</span>}
                </div>
                <button
                  onClick={() => handleSync(s.id)}
                  disabled={syncingId === s.id}
                  className="rounded border border-slate-700 px-2 py-1 text-xs hover:bg-slate-800 disabled:opacity-50"
                >
                  {syncingId === s.id ? "Syncing…" : "Sync"}
                </button>
              </div>
              <div className="mt-1 text-slate-500">
                {s.type} · {s.status}
                {s.last_successful_sync_at && ` · last synced ${s.last_successful_sync_at}`}
              </div>
              {s.last_error && <div className="mt-1 text-red-400">{s.last_error}</div>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
