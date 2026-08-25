"use client";

import type { LegalResearchResult, ResearchStatus, ResearchTrace } from "@/types/legal";
import { Badge, Card, CardHeader, Notice } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

const CONFIDENCE_TONE: Record<string, BadgeTone> = { high: "green", medium: "amber", low: "red" };

const CLAIM_STATUS_LABEL: Record<string, { label: string; tone: BadgeTone }> = {
  verified: { label: "Verified", tone: "green" },
  mock: { label: "Mock", tone: "amber" },
  unverified: { label: "Unverified", tone: "gray" },
  unsupported_critical: { label: "Unsupported (critical)", tone: "red" },
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
    <div className="space-y-5">
      <Card>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">Conclusion</h2>
          <Badge tone={CONFIDENCE_TONE[result.confidence] ?? "gray"}>Confidence: {result.confidence}</Badge>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-slate-700">{result.executive_conclusion}</p>
        {status !== "completed" && <p className="mt-2 text-sm text-warning">Status: {status}</p>}
        {result.escalate_to_human && (
          <div className="mt-3">
            <Notice tone="danger">Human legal review recommended: {result.escalation_reasons.join("; ")}</Notice>
          </div>
        )}
      </Card>

      {result.issues.length > 0 && (
        <Card>
          <CardHeader title="Legal Issues" />
          <ul className="space-y-1.5 text-sm text-slate-700">
            {result.issues.map((issue) => (
              <li key={issue.id}>
                <span className="text-muted">[{issue.issue_type}]</span> {issue.title}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {result.analysis.length > 0 && (
        <Card>
          <CardHeader title="Analysis" />
          <ul className="space-y-2 text-sm text-slate-700">
            {result.analysis.map((line, idx) => (
              <li key={idx}>{line}</li>
            ))}
          </ul>
        </Card>
      )}

      {result.counterarguments.length > 0 && (
        <Card>
          <CardHeader title="Counterarguments" />
          <ul className="space-y-1.5 text-sm text-slate-700">
            {result.counterarguments.map((c, idx) => (
              <li key={idx}>{c}</li>
            ))}
          </ul>
        </Card>
      )}

      {result.conflicts.length > 0 && (
        <Card>
          <CardHeader title="Conflicting Practice" />
          <div className="space-y-2.5">
            {result.conflicts.map((c, idx) => (
              <div key={idx} className="rounded-xl border border-amber-200 bg-warning-soft p-3.5 text-sm">
                <div className="font-semibold text-warning">{c.conflict_type}</div>
                <div className="mt-1 text-slate-700">Позиция A: {c.position_a}</div>
                <div className="mt-1 text-slate-700">Позиция B: {c.position_b}</div>
                {c.implication && <div className="mt-1 text-muted">{c.implication}</div>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {result.risks.length > 0 && (
        <Card>
          <CardHeader title="Risks" />
          <ul className="space-y-1.5 text-sm text-slate-700">
            {result.risks.map((r, idx) => (
              <li key={idx}>{r}</li>
            ))}
          </ul>
        </Card>
      )}

      {result.missing_facts.length > 0 && (
        <Card>
          <CardHeader title="Missing Facts" />
          <ul className="space-y-1.5 text-sm text-slate-700">
            {result.missing_facts.map((m, idx) => (
              <li key={idx}>
                <span className="text-muted">[{m.criticality}]</span> {m.question}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader title={`Sources (${Math.round(result.citation_coverage * 100)}% citation coverage)`} />
        <div className="space-y-2.5">
          {result.claims
            .filter((c) => c.claim_type === "rule")
            .map((claim, idx) => {
              const claimStatus = CLAIM_STATUS_LABEL[claim.verification_status] ?? CLAIM_STATUS_LABEL.unverified;
              return (
                <div key={idx} className="rounded-xl border border-line p-3.5 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-ink">{claim.citations.join(", ") || "(unverified)"}</span>
                    <Badge tone={claimStatus.tone}>{claimStatus.label}</Badge>
                  </div>
                  <div className="mt-1 text-muted">{claim.claim}</div>
                </div>
              );
            })}
        </div>
      </Card>

      {result.recommended_actions.length > 0 && (
        <Card>
          <CardHeader title="Recommended Actions" />
          <ul className="space-y-1.5 text-sm text-slate-700">
            {result.recommended_actions.map((a, idx) => (
              <li key={idx}>{a}</li>
            ))}
          </ul>
        </Card>
      )}

      {trace && (
        <details className="rounded-xl border border-line bg-panel-muted p-3.5 text-sm text-muted">
          <summary className="cursor-pointer font-medium text-slate-700">
            Research details ({trace.retrieved_count} sources retrieved, {trace.llm_calls} reasoning steps)
          </summary>
          <div className="mt-3 space-y-2">
            <div>
              <span className="text-muted">Queries: </span>
              {trace.queries.join("; ")}
            </div>
            {trace.knowledge_snapshot && (
              <div className="text-muted">
                Knowledge base at time of research: {trace.knowledge_snapshot.total_chunks} chunks (
                {trace.knowledge_snapshot.mock_chunks} mock)
              </div>
            )}
            <div className="text-muted">
              Timing: {Object.entries(trace.performance_ms).map(([k, v]) => `${k}=${Math.round(v)}ms`).join(", ")}
            </div>
          </div>
        </details>
      )}
    </div>
  );
}
