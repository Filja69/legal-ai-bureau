"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { runResearch } from "@/api/legal";
import { listResearchReports } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import type { LegalResearchResponse } from "@/types/legal";
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
    return <div className="p-8 text-sm text-slate-500">Select a workspace to run research.</div>;
  }

  return (
    <div className="mx-auto grid max-w-6xl grid-cols-1 gap-8 p-8 lg:grid-cols-[280px_1fr]">
      <aside>
        <h2 className="text-sm font-semibold text-slate-300">Past Research</h2>
        {!historyQuery.data && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
        {historyQuery.data?.items.length === 0 && <p className="mt-2 text-sm text-slate-500">No research yet.</p>}
        <ul className="mt-2 space-y-2">
          {historyQuery.data?.items.map((r) => (
            <li key={r.id}>
              <Link href={`/research/${r.id}`} className="block rounded border border-slate-800 p-2 text-xs hover:border-slate-600">
                <div className="line-clamp-2 text-slate-300">{r.question}</div>
                <div className="mt-1 text-slate-500">
                  {r.confidence} confidence · {new Date(r.created_at).toLocaleDateString()}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </aside>

      <div>
        <h1 className="text-2xl font-semibold">Legal Research</h1>
        <p className="mt-1 text-sm text-slate-400">
          Multi-stage Legal Research Engine — fact extraction, issue identification, retrieval, IRAC
          reasoning, counterarguments, conflict detection, independent review.
        </p>

        <div className="mt-6 space-y-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Describe your legal question"
            rows={4}
            className="w-full rounded border border-slate-700 bg-slate-900 p-3 text-sm"
          />
          <div className="flex items-center gap-4 text-sm text-slate-400">
            <span>Jurisdiction: Russia</span>
            <label className="flex items-center gap-2">
              Date:
              <input
                type="date"
                value={effectiveAt}
                onChange={(e) => setEffectiveAt(e.target.value)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200"
              />
            </label>
          </div>
          <button
            onClick={handleStart}
            disabled={loading || !question.trim()}
            className="rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
          >
            {loading ? "Researching..." : "Start Research"}
          </button>
        </div>

        {error && <p className="mt-6 text-sm text-red-400">{error}</p>}

        {response && (
          <div className="mt-10 border-t border-slate-800 pt-8">
            <ResearchResult status={response.status} result={response.result} trace={response.trace} />
          </div>
        )}
      </div>
    </div>
  );
}
