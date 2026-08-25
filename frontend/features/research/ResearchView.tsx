"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { runResearch } from "@/api/legal";
import { listResearchReports } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import type { LegalResearchResponse } from "@/types/legal";
import { Button, Card, PageHeader } from "@/components/ui";
import { ResearchResult } from "./ResearchResult";

export function ResearchView() {
  const { workspaceId } = useAuth();
  const searchParams = useSearchParams();
  // Prefill from the Assistant composer's honest routing (?q=...) — never
  // auto-submitted: a question this expensive (real fact extraction +
  // retrieval + IRAC reasoning) should only ever run when the user
  // deliberately confirms it, not the instant they land on the page.
  const [question, setQuestion] = useState(searchParams.get("q") ?? "");
  const [effectiveAt, setEffectiveAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<LegalResearchResponse | null>(null);

  const historyQuery = useQuery({
    queryKey: ["research", "history", workspaceId],
    queryFn: () => listResearchReports(workspaceId!, { limit: 20 }),
    enabled: !!workspaceId,
  });

  async function handleStart() {
    if (!question.trim() || !workspaceId) return;
    setLoading(true);
    setError(null);
    setResponse(null);
    try {
      const result = await runResearch({
        workspaceId,
        question,
        effectiveAt: effectiveAt || null,
      });
      setResponse(result);
      await historyQuery.refetch();
    } catch {
      setError("Research failed — is the backend running and is the Knowledge Base populated?");
    } finally {
      setLoading(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Select a workspace to run research.</div>;
  }

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-6 p-4 sm:p-8 lg:grid-cols-[280px_1fr]">
      <aside>
        <h2 className="mb-3 text-sm font-semibold text-ink">Past Research</h2>
        {!historyQuery.data && <p className="text-sm text-muted">Loading…</p>}
        {historyQuery.data?.items.length === 0 && <p className="text-sm text-muted">No research yet.</p>}
        <div className="space-y-2">
          {historyQuery.data?.items.map((r) => (
            <Link key={r.id} href={`/research/${r.id}`}>
              <Card className="p-3 transition-shadow hover:shadow-panel">
                <div className="line-clamp-2 text-xs font-medium text-ink">{r.question}</div>
                <div className="mt-1 text-xs text-muted">
                  {r.confidence} confidence · {new Date(r.created_at).toLocaleDateString()}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </aside>

      <div>
        <PageHeader
          title="Legal Research"
          description="Multi-stage Legal Research Engine — fact extraction, issue identification, retrieval, IRAC reasoning, counterarguments, conflict detection, independent review."
        />

        <Card className="space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Describe your legal question"
            rows={4}
            className="w-full rounded-lg border border-line bg-white p-3 text-sm text-ink placeholder:text-slate-400"
          />
          <div className="flex flex-wrap items-center gap-4 text-sm text-muted">
            <span>Jurisdiction: Russia</span>
            <label className="flex items-center gap-2">
              Date:
              <input
                type="date"
                value={effectiveAt}
                onChange={(e) => setEffectiveAt(e.target.value)}
                className="rounded-lg border border-line bg-white px-2 py-1 text-ink"
              />
            </label>
          </div>
          <Button variant="primary" onClick={handleStart} disabled={loading || !question.trim()}>
            {loading ? "Researching..." : "Start Research"}
          </Button>
        </Card>

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}

        {response && (
          <div className="mt-8">
            <ResearchResult status={response.status} result={response.result} trace={response.trace} />
          </div>
        )}
      </div>
    </div>
  );
}
