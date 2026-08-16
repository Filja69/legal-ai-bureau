"use client";

import type { LegalResearchResult, ResearchStatus, ResearchTrace } from "@/types/legal";

const CONFIDENCE_COLOR: Record<string, string> = {
  high: "text-emerald-400",
  medium: "text-amber-400",
  low: "text-red-400",
};

const CLAIM_STATUS_LABEL: Record<string, { label: string; className: string }> = {
  verified: { label: "Verified", className: "bg-emerald-900 text-emerald-300" },
  mock: { label: "Mock", className: "bg-amber-900 text-amber-300" },
  unverified: { label: "Unverified", className: "bg-slate-700 text-slate-300" },
  unsupported_critical: { label: "Unsupported (critical)", className: "bg-red-900 text-red-300" },
};

// Shared render of a Legal Research Engine result — used by both the
// just-ran view (ResearchView) and the persisted-report detail page
// (app/research/[id]) so the two never drift in what they show.
export function ResearchResult({
  status,
  result,
  trace,
}: {
  status: ResearchStatus;
  result: LegalResearchResult;
  trace?: ResearchTrace;
}) {
  return (
    <div className="space-y-8">
      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Conclusion</h2>
          <span className={`text-sm font-semibold uppercase ${CONFIDENCE_COLOR[result.confidence]}`}>
            Confidence: {result.confidence}
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-200">{result.executive_conclusion}</p>
        {status !== "completed" && <p className="mt-2 text-sm text-amber-400">Status: {status}</p>}
        {result.escalate_to_human && (
          <p className="mt-2 text-sm text-red-400">
            Human legal review recommended: {result.escalation_reasons.join("; ")}
          </p>
        )}
      </section>

      {result.issues.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Legal Issues</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {result.issues.map((issue) => (
              <li key={issue.id}>
                <span className="text-slate-500">[{issue.issue_type}]</span> {issue.title}
              </li>
            ))}
          </ul>
        </section>
      )}

      {result.analysis.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Analysis</h2>
          <ul className="mt-2 space-y-2 text-sm text-slate-300">
            {result.analysis.map((line, idx) => (
              <li key={idx}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      {result.counterarguments.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Counterarguments</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {result.counterarguments.map((c, idx) => (
              <li key={idx}>{c}</li>
            ))}
          </ul>
        </section>
      )}

      {result.conflicts.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Conflicting Practice</h2>
          {result.conflicts.map((c, idx) => (
            <div key={idx} className="mt-2 rounded border border-amber-900 bg-amber-950/30 p-3 text-sm">
              <div className="font-medium text-amber-300">{c.conflict_type}</div>
              <div className="mt-1 text-slate-300">Позиция A: {c.position_a}</div>
              <div className="mt-1 text-slate-300">Позиция B: {c.position_b}</div>
              {c.implication && <div className="mt-1 text-slate-400">{c.implication}</div>}
            </div>
          ))}
        </section>
      )}

      {result.risks.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Risks</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {result.risks.map((r, idx) => (
              <li key={idx}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      {result.missing_facts.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Missing Facts</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {result.missing_facts.map((m, idx) => (
              <li key={idx}>
                <span className="text-slate-500">[{m.criticality}]</span> {m.question}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="text-lg font-medium">Sources ({Math.round(result.citation_coverage * 100)}% citation coverage)</h2>
        <ul className="mt-2 space-y-2">
          {result.claims
            .filter((c) => c.claim_type === "rule")
            .map((claim, idx) => {
              const claimStatus = CLAIM_STATUS_LABEL[claim.verification_status] ?? CLAIM_STATUS_LABEL.unverified;
              return (
                <li key={idx} className="rounded border border-slate-800 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-200">{claim.citations.join(", ") || "(unverified)"}</span>
                    <span className={`rounded px-2 py-0.5 text-xs ${claimStatus.className}`}>{claimStatus.label}</span>
                  </div>
                  <div className="mt-1 text-slate-400">{claim.claim}</div>
                </li>
              );
            })}
        </ul>
      </section>

      {result.recommended_actions.length > 0 && (
        <section>
          <h2 className="text-lg font-medium">Recommended Actions</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {result.recommended_actions.map((a, idx) => (
              <li key={idx}>{a}</li>
            ))}
          </ul>
        </section>
      )}

      {trace && (
        <details className="rounded border border-slate-800 p-3 text-sm text-slate-400">
          <summary className="cursor-pointer text-slate-300">
            Research details ({trace.retrieved_count} sources retrieved, {trace.llm_calls} reasoning steps)
          </summary>
          <div className="mt-3 space-y-2">
            <div>
              <span className="text-slate-500">Queries: </span>
              {trace.queries.join("; ")}
            </div>
            {trace.knowledge_snapshot && (
              <div className="text-slate-500">
                Knowledge base at time of research: {trace.knowledge_snapshot.total_chunks} chunks (
                {trace.knowledge_snapshot.mock_chunks} mock)
              </div>
            )}
            <div className="text-slate-500">
              Timing: {Object.entries(trace.performance_ms).map(([k, v]) => `${k}=${Math.round(v)}ms`).join(", ")}
            </div>
          </div>
        </details>
      )}
    </div>
  );
}
