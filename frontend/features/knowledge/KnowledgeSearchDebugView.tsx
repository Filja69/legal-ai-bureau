"use client";

import axios from "axios";
import { useState } from "react";
import { searchDebug, type SearchDebugResult } from "@/api/knowledge";
import { Button, Card, CardHeader, Notice, PageHeader } from "@/components/ui";
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
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader title="Knowledge Base" />
      <div className="mb-4">
        <KnowledgeNav />
      </div>

      <p className="mb-4 text-xs text-muted">
        Retrieval diagnostics only — shows which candidates keyword/vector search found, fusion scores, and timings.
        Never exposes LLM chain-of-thought (this endpoint doesn&apos;t call an LLM).
      </p>

      <Card className="mb-6">
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Debug query"
            className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink"
          />
          <Button variant="primary" onClick={handleSearch} disabled={loading || !query.trim()}>
            {loading ? "Running…" : "Run"}
          </Button>
        </div>
        {error && (
          <div className="mt-2">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}
      </Card>

      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Card>
              <div className="text-xs text-muted">Embedding</div>
              <div className="mt-1 text-sm text-ink">
                {result.embedding.provider}/{result.embedding.model} · namespace {result.embedding.namespace}
              </div>
            </Card>
            <Card>
              <div className="text-xs text-muted">Latency (ms)</div>
              <div className="mt-1 text-sm text-ink">
                {Object.entries(result.latency_ms).map(([k, v]) => `${k}=${v}`).join(", ")}
              </div>
            </Card>
          </div>
          <Card>
            <CardHeader title={`Hybrid results (${result.fusion.candidate_count} candidates fused)`} />
            <ul className="space-y-1.5">
              {result.hybrid_results.map((r, idx) => (
                <li key={idx} className="rounded-lg border border-line p-2.5">
                  <div className="flex justify-between">
                    <span className="text-sm text-ink">{r.title}</span>
                    <span className="text-xs text-muted">
                      {r.score.toFixed(3)} · {r.retrieval_mode}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
          {result.citation_validation.length > 0 && (
            <Card>
              <CardHeader title="Citation validation" />
              <ul className="space-y-1.5 text-sm text-slate-600">
                {result.citation_validation.map((c, idx) => (
                  <li key={idx}>
                    {c.law_short_name} ст. {c.article_number} — {c.status}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
