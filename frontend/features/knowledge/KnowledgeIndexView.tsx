"use client";

import axios from "axios";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listKnowledgeDocuments, reindexKnowledgeBase, type ReindexReport } from "@/api/knowledge";
import { Badge, Button, Card, CardHeader, Notice, PageHeader } from "@/components/ui";
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
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader title="Knowledge Base" />
      <div className="mb-6">
        <KnowledgeNav />
      </div>

      <Card className="mb-6">
        <CardHeader title="Reindex (dry run)" description="Preview only — never writes. A real reindex must be run from the backend/ops tooling, not this UI, to avoid accidental cost/blast radius from the browser." />
        <Button onClick={handleDryRun} disabled={reindexing}>
          {reindexing ? "Running…" : "Run dry-run preview"}
        </Button>
        {reindexError && (
          <div className="mt-2">
            <Notice tone="danger">{reindexError}</Notice>
          </div>
        )}
        {reindexReport && (
          <dl className="mt-3 grid grid-cols-2 gap-1.5 text-xs text-muted">
            <dt>Target namespace</dt>
            <dd className="text-ink">{reindexReport.target_namespace}</dd>
            <dt>Would reindex</dt>
            <dd className="text-ink">{reindexReport.would_reindex}</dd>
            <dt>Already current</dt>
            <dd className="text-ink">{reindexReport.already_current}</dd>
            <dt>Ready to activate</dt>
            <dd className="text-ink">{reindexReport.ready_to_activate ? "yes" : "no"}</dd>
          </dl>
        )}
      </Card>

      <Card>
        <CardHeader title="Indexed Chunks" />
        {documentsQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {isForbidden && <Notice tone="danger">Admin or Owner role required.</Notice>}
        {documentsQuery.isError && !isForbidden && <Notice tone="danger">Could not load index.</Notice>}
        <ul className="space-y-1.5 text-sm">
          {documentsQuery.data?.map((d) => (
            <li key={d.chunk_id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2">
              <span className="text-slate-700">
                {d.document_type} {d.article_number ? `· art. ${d.article_number}` : ""}
              </span>
              <span className="flex items-center gap-2 text-xs text-muted">
                {d.embedding_model}
                {d.is_mock && <Badge tone="amber">MOCK</Badge>}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
