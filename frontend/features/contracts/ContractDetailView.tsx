"use client";

import { useEffect, useState } from "react";
import {
  analyzeContract,
  decideRedlineChange,
  getContract,
  getContractClauses,
  getContractReport,
  getRedline,
  listContractVersions,
} from "@/api/contracts";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/hooks/useAuth";
import type { Contract, ContractClause, ContractReport, ContractVersion, RedlineChange } from "@/types/contract";
import { Badge, Button, Card, CardHeader, Notice, toneForSeverity } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

const SEVERITY_TONE: Record<string, BadgeTone> = { critical: "red", high: "amber", medium: "amber", low: "gray", info: "gray" };

const TABS = ["Overview", "Clauses", "Risks", "Research", "Redline", "Versions", "Audit"] as const;
type Tab = (typeof TABS)[number];

function DiffView({ diffOps }: { diffOps: RedlineChange["diff_ops"] }) {
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {diffOps.map((op, idx) => {
        if (op.op === "equal") return <span key={idx}>{op.text}</span>;
        if (op.op === "delete") {
          return (
            <span key={idx} className="bg-danger-soft text-danger line-through">
              {op.text}
            </span>
          );
        }
        return (
          <span key={idx} className="bg-success-soft text-success">
            {op.text}
          </span>
        );
      })}
    </p>
  );
}

export function ContractDetailView({ contractId }: { contractId: string }) {
  const { workspaceId } = useAuth();
  const [contract, setContract] = useState<Contract | null>(null);
  const [report, setReport] = useState<ContractReport | null>(null);
  const [clauses, setClauses] = useState<ContractClause[]>([]);
  const [redline, setRedline] = useState<RedlineChange[] | null>(null);
  const [versions, setVersions] = useState<ContractVersion[]>([]);
  const [selectedClauseId, setSelectedClauseId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decidingId, setDecidingId] = useState<string | null>(null);

  async function loadContract() {
    if (!workspaceId) return;
    try {
      setContract(await getContract(workspaceId, contractId));
    } catch {
      setError("Contract not found.");
    }
  }

  async function loadReport() {
    if (!workspaceId) return;
    try {
      const [r, c] = await Promise.all([
        getContractReport(workspaceId, contractId),
        getContractClauses(workspaceId, contractId),
      ]);
      setReport(r);
      setClauses(c);
    } catch {
      // No report yet — analyze() below handles the first-run case.
    }
  }

  async function loadRedline() {
    if (!workspaceId) return;
    try {
      setRedline(await getRedline(workspaceId, contractId));
    } catch {
      setRedline([]);
    }
  }

  async function loadVersions() {
    if (!workspaceId) return;
    try {
      setVersions(await listContractVersions(workspaceId, contractId));
    } catch {
      setVersions([]);
    }
  }

  useEffect(() => {
    loadContract();
    loadReport();
    loadVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contractId, workspaceId]);

  useEffect(() => {
    if (tab === "Redline" && redline === null) loadRedline();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, workspaceId]);

  async function handleAnalyze() {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      await analyzeContract(workspaceId, contractId);
      await loadReport();
    } catch {
      setError("Analysis failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleDecision(changeId: string, decision: "accepted" | "rejected") {
    if (!workspaceId) return;
    setDecidingId(changeId);
    try {
      await decideRedlineChange(workspaceId, contractId, changeId, decision);
      await loadRedline();
    } catch {
      setError("Could not record redline decision.");
    } finally {
      setDecidingId(null);
    }
  }

  const selectedClause = clauses.find((c) => c.id === selectedClauseId) ?? null;

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Select a workspace to view this contract.</div>;
  }

  const missingClauseRisks = report?.risks.filter((r) => r.risk_type === "missing_clause") ?? [];

  return (
    <div className="mx-auto max-w-6xl p-4 sm:p-8">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold text-ink">{contract?.title ?? "Contract"}</h1>
        {contract?.is_mock && <Badge tone="amber">MOCK</Badge>}
      </div>
      {contract && (
        <p className="mt-1 text-sm text-muted">
          {contract.contract_type} · {contract.status}
        </p>
      )}

      {!report && (
        <div className="mt-4">
          <Button variant="primary" onClick={handleAnalyze} disabled={loading}>
            {loading ? "Analyzing..." : "Analyze Contract"}
          </Button>
        </div>
      )}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      {report && (
        <>
          <div className="mt-5 flex w-fit gap-1 overflow-x-auto rounded-xl border border-line bg-panel-muted p-1 text-sm">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`shrink-0 rounded-lg px-3.5 py-1.5 font-medium transition-colors ${
                  tab === t ? "bg-white text-ink shadow-sm" : "text-muted hover:text-ink"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="mt-5">
            {tab === "Overview" && (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                <div className="space-y-4 lg:col-span-1">
                  <Card>
                    <CardHeader title="Risk Summary" />
                    <div className="space-y-1.5 text-sm">
                      {(["critical", "high", "medium", "low", "info"] as const).map((sev) => (
                        <div key={sev} className="flex items-center justify-between rounded-lg border border-line px-2.5 py-1.5">
                          <Badge tone={SEVERITY_TONE[sev]}>{sev}</Badge>
                          <span className="font-semibold text-ink">{report.risk_summary[sev] ?? 0}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                  <Card>
                    <div className="text-xs text-muted">Overall Score</div>
                    <div className="mt-1 text-2xl font-semibold text-ink">{report.overall_score}/100</div>
                    {report.analysis_status === "stale" && (
                      <div className="mt-3">
                        <Notice tone="warning">This contract was edited since the last analysis — re-analyze for current results.</Notice>
                      </div>
                    )}
                  </Card>
                </div>
                <Card className="lg:col-span-2">
                  <CardHeader title="Executive Summary" />
                  <p className="text-sm leading-relaxed text-slate-700">{report.executive_summary}</p>
                </Card>
              </div>
            )}

            {tab === "Clauses" && (
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                <Card className="lg:col-span-1">
                  <ul className="space-y-1 text-sm">
                    {clauses.map((c) => (
                      <li key={c.id}>
                        <button
                          onClick={() => setSelectedClauseId(c.id)}
                          className={`w-full rounded-lg border px-2.5 py-1.5 text-left ${
                            selectedClauseId === c.id ? "border-blue-300 bg-brand-soft" : "border-line hover:bg-panel-muted"
                          }`}
                        >
                          {c.clause_number ?? "—"} · {c.clause_type}
                        </button>
                      </li>
                    ))}
                  </ul>
                </Card>
                <Card className="lg:col-span-2">
                  {selectedClause ? (
                    <div className="text-sm text-slate-700">
                      <div className="text-xs text-muted">
                        Clause {selectedClause.clause_number} · confidence {Math.round(selectedClause.confidence * 100)}%
                      </div>
                      <p className="mt-2 whitespace-pre-wrap">{selectedClause.original_text}</p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted">Select a clause to view its text.</p>
                  )}
                </Card>
              </div>
            )}

            {tab === "Risks" && (
              <div className="space-y-3">
                <h2 className="text-lg font-semibold text-ink">Risks &amp; Missing Clauses</h2>
                {report.risks.map((risk) => (
                  <Card key={risk.id}>
                    <div className="flex items-center justify-between gap-2">
                      <Badge tone={SEVERITY_TONE[risk.severity]}>{risk.severity}</Badge>
                      <StatusBadge status={risk.verification_status} />
                    </div>
                    <div className="mt-1.5 font-semibold text-ink">{risk.title}</div>
                    <div className="mt-1 text-sm text-slate-700">{risk.description}</div>
                    {risk.why_it_matters && <div className="mt-1 text-xs text-muted">Почему это важно: {risk.why_it_matters}</div>}
                    {risk.legal_basis && <div className="mt-1 text-xs text-muted">Правовое основание: {risk.legal_basis}</div>}
                    {risk.recommendation && (
                      <div className="mt-1 text-xs text-muted">
                        Рекомендация ({risk.recommendation.action}): {risk.recommendation.reason}
                      </div>
                    )}
                    {risk.alternative_clause && (
                      <div className="mt-2 rounded-lg bg-panel-muted p-2.5 text-sm text-slate-700">
                        <div className="text-xs text-muted">Предлагаемая редакция:</div>
                        {risk.alternative_clause.proposed_text}
                      </div>
                    )}
                    <div className="mt-2.5 flex gap-2">
                      {risk.clause_id && (
                        <button
                          onClick={() => {
                            setTab("Clauses");
                            setSelectedClauseId(risk.clause_id);
                          }}
                          className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-panel-muted"
                        >
                          View Clause
                        </button>
                      )}
                      {risk.citations.length > 0 && <Badge tone="gray">{risk.citations.join(", ")}</Badge>}
                    </div>
                  </Card>
                ))}
                {missingClauseRisks.length === 0 && <p className="text-xs text-muted">No missing-clause coverage gaps flagged.</p>}
              </div>
            )}

            {tab === "Research" && (
              <Notice tone="info">
                Risk verification is backed by the Legal Research Engine internally — each risk&apos;s citations above
                come from verified research, but individual per-risk research reports aren&apos;t separately browsable
                yet. Use the Legal Research workspace to run new research on this contract&apos;s subject matter.
              </Notice>
            )}

            {tab === "Redline" && (
              <div className="space-y-4">
                <p className="text-xs text-muted">
                  AI proposes changes below; nothing is applied to the document automatically. Accept or reject each
                  change explicitly.
                </p>
                {redline === null && <p className="text-sm text-muted">Loading…</p>}
                {redline?.length === 0 && <p className="text-sm text-muted">No redline changes proposed.</p>}
                {redline?.map((change) => (
                  <Card key={change.id}>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted">{change.reason}</span>
                      <Badge tone={toneForSeverity(change.review_status)}>{change.review_status}</Badge>
                    </div>
                    <div className="mt-2 rounded-lg bg-panel-muted p-2.5">
                      <DiffView diffOps={change.diff_ops} />
                    </div>
                    {change.review_status === "proposed" && (
                      <div className="mt-2.5 flex gap-2">
                        <button
                          onClick={() => handleDecision(change.id, "accepted")}
                          disabled={decidingId === change.id}
                          className="rounded-lg border border-emerald-200 px-2.5 py-1 text-xs font-medium text-success hover:bg-success-soft disabled:opacity-50"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => handleDecision(change.id, "rejected")}
                          disabled={decidingId === change.id}
                          className="rounded-lg border border-red-200 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger-soft disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}

            {tab === "Versions" && (
              <Card>
                <ul className="space-y-2 text-sm">
                  {versions.map((v) => (
                    <li key={v.id} className="flex items-center justify-between rounded-lg border border-line p-3">
                      <span className="text-ink">
                        v{v.version_number} {v.is_current && <span className="text-success">(current)</span>}
                      </span>
                      <span className="text-xs text-muted">{new Date(v.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
                {versions.length < 2 && (
                  <p className="mt-3 text-xs text-muted">
                    Only one version exists — version comparison becomes available once the contract is re-uploaded.
                  </p>
                )}
              </Card>
            )}

            {tab === "Audit" && (
              <Notice tone="info">
                Per-contract audit trail UI is not implemented yet — analysis and redline-decision events are logged
                server-side (structured logs), not yet exposed through a dedicated API.
              </Notice>
            )}
          </div>
        </>
      )}
    </div>
  );
}
