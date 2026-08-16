"use client";

import axios from "axios";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listKnowledgeDocuments, reindexKnowledgeBase, type ReindexReport } from "@/api/knowledge";
import { KnowledgeNav } from "./KnowledgeNav";

export function KnowledgeIndexView() {
  const [reindexing, setReindexing] = useState(false);
  const [reindexReport, setReindexReport] = useState<ReindexReport | null>(null);
  const [reindexError, setReindexError] = useState<string | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["knowledge", "documents"],
    queryFn: () => listKnowledgeDocuments(100),
    retry: false,
  });
  const isForbidden = axios.isAxiosError(documentsQuery.error) && documentsQuery.error.response?.status === 403;

  async function handleDryRun() {
    setReindexing(true);
    setReindexError(null);
    setReindexReport(null);
    try {
      setReindexReport(await reindexKnowledgeBase(true));
    } catch {
      setReindexError("Dry-run reindex failed.");
    } finally {
      setReindexing(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Knowledge Base</h1>
      <div className="mt-4">
        <KnowledgeNav />
      </div>

      <div className="mt-6 rounded border border-slate-800 p-4">
        <h2 className="text-sm font-semibold text-slate-300">Reindex (dry run)</h2>
        <p className="mt-1 text-xs text-slate-500">
          Preview only — never writes. A real reindex must be run from the backend/ops tooling, not this UI, to avoid
          accidental cost/blast radius from the browser.
        </p>
        <button
          onClick={handleDryRun}
          disabled={reindexing}
          className="mt-3 rounded border border-slate-700 px-3 py-1.5 text-xs hover:bg-slate-800 disabled:opacity-50"
        >
          {reindexing ? "Running…" : "Run dry-run preview"}
        </button>
        {reindexError && <p className="mt-2 text-sm text-red-400">{reindexError}</p>}
        {reindexReport && (
          <dl className="mt-3 grid grid-cols-2 gap-1 text-xs text-slate-400">
            <dt>Target namespace</dt>
            <dd className="text-slate-200">{reindexReport.target_namespace}</dd>
            <dt>Would reindex</dt>
            <dd className="text-slate-200">{reindexReport.would_reindex}</dd>
            <dt>Already current</dt>
            <dd className="text-slate-200">{reindexReport.already_current}</dd>
            <dt>Ready to activate</dt>
            <dd className="text-slate-200">{reindexReport.ready_to_activate ? "yes" : "no"}</dd>
          </dl>
        )}
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-slate-300">Indexed Chunks</h2>
        {documentsQuery.isLoading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
        {isForbidden && <p className="mt-2 text-sm text-red-400">Admin or Owner role required.</p>}
        {documentsQuery.isError && !isForbidden && <p className="mt-2 text-sm text-red-400">Could not load index.</p>}
        <ul className="mt-2 space-y-1 text-sm">
          {documentsQuery.data?.map((d) => (
            <li key={d.chunk_id} className="flex items-center justify-between rounded border border-slate-800 px-3 py-2">
              <span className="text-slate-300">
                {d.document_type} {d.article_number ? `· art. ${d.article_number}` : ""}
              </span>
              <span className="text-xs text-slate-500">
                {d.embedding_model}
                {d.is_mock && <span className="ml-2 rounded bg-amber-900 px-1.5 py-0.5 text-amber-300">MOCK</span>}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
