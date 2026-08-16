"use client";

import axios from "axios";
import { useState } from "react";
import { searchDebug, type SearchDebugResult } from "@/api/knowledge";
import { KnowledgeNav } from "./KnowledgeNav";

export function KnowledgeSearchDebugView() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchDebugResult | null>(null);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await searchDebug(query));
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 403) {
        setError("Admin or Owner role required to use Search Debug.");
      } else {
        setError("Search debug failed.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-8">
      <h1 className="text-2xl font-semibold">Knowledge Base</h1>
      <div className="mt-4">
        <KnowledgeNav />
      </div>

      <p className="mt-4 text-xs text-slate-500">
        Retrieval diagnostics only — shows which candidates keyword/vector search found, fusion scores, and timings.
        Never exposes LLM chain-of-thought (this endpoint doesn&apos;t call an LLM).
      </p>

      <div className="mt-4 flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Debug query"
          className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        />
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
        >
          {loading ? "Running…" : "Run"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

      {result && (
        <div className="mt-6 space-y-4 text-sm">
          <div className="rounded border border-slate-800 p-3">
            <div className="text-xs text-slate-500">Embedding</div>
            <div className="text-slate-300">
              {result.embedding.provider}/{result.embedding.model} · namespace {result.embedding.namespace}
            </div>
          </div>
          <div className="rounded border border-slate-800 p-3">
            <div className="text-xs text-slate-500">Latency (ms)</div>
            <div className="text-slate-300">
              {Object.entries(result.latency_ms).map(([k, v]) => `${k}=${v}`).join(", ")}
            </div>
          </div>
          <div>
            <h2 className="font-medium text-slate-200">Hybrid results ({result.fusion.candidate_count} candidates fused)</h2>
            <ul className="mt-2 space-y-1">
              {result.hybrid_results.map((r, idx) => (
                <li key={idx} className="rounded border border-slate-800 p-2">
                  <div className="flex justify-between">
                    <span className="text-slate-300">{r.title}</span>
                    <span className="text-xs text-slate-500">{r.score.toFixed(3)} · {r.retrieval_mode}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          {result.citation_validation.length > 0 && (
            <div>
              <h2 className="font-medium text-slate-200">Citation validation</h2>
              <ul className="mt-2 space-y-1">
                {result.citation_validation.map((c, idx) => (
                  <li key={idx} className="text-slate-400">
                    {c.law_short_name} ст. {c.article_number} — {c.status}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
