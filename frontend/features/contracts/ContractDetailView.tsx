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

const SEVERITY_COLOR: Record<string, string> = {
  critical: "border-red-700 bg-red-950/40 text-red-300",
  high: "border-orange-700 bg-orange-950/40 text-orange-300",
  medium: "border-amber-700 bg-amber-950/40 text-amber-300",
  low: "border-slate-700 bg-slate-900 text-slate-300",
  info: "border-slate-800 bg-slate-900 text-slate-500",
};

const TABS = ["Overview", "Clauses", "Risks", "Research", "Redline", "Versions", "Audit"] as const;
type Tab = (typeof TABS)[number];

function DiffView({ diffOps }: { diffOps: RedlineChange["diff_ops"] }) {
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {diffOps.map((op, idx) => {
        if (op.op === "equal") return <span key={idx}>{op.text}</span>;
        if (op.op === "delete") {
          return (
            <span key={idx} className="bg-red-950/60 text-red-300 line-through">
              {op.text}
            </span>
          );
        }
        return (
          <span key={idx} className="bg-emerald-950/60 text-emerald-300">
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
    return <div className="p-8 text-sm text-slate-500">Select a workspace to view this contract.</div>;
  }

  const missingClauseRisks = report?.risks.filter((r) => r.risk_type === "missing_clause") ?? [];

  return (
    <div className="mx-auto max-w-5xl p-8">
      <h1 className="text-2xl font-semibold">{contract?.title ?? "Contract"}</h1>
      {contract && (
        <p className="mt-1 text-sm text-slate-400">
          {contract.contract_type} · {contract.status}
          {contract.is_mock && <span className="ml-2 rounded bg-amber-900 px-1.5 py-0.5 text-xs text-amber-300">MOCK</span>}
        </p>
      )}

      {!report && (
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="mt-4 rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
        >
          {loading ? "Analyzing..." : "Analyze Contract"}
        </button>
      )}
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

      {report && (
        <>
          <div className="mt-6 flex gap-1 border-b border-slate-800 text-sm">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-2 ${
                  tab === t ? "border-b-2 border-slate-200 text-slate-100" : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="mt-6">
            {tab === "Overview" && (
              <div className="grid grid-cols-3 gap-6">
                <div className="col-span-1">
                  <h2 className="text-lg font-medium">Risk Summary</h2>
                  <div className="mt-2 space-y-1 text-sm">
                    {(["critical", "high", "medium", "low", "info"] as const).map((sev) => (
                      <div key={sev} className="flex items-center justify-between rounded border border-slate-800 px-2 py-1">
                        <span className="uppercase text-slate-400">{sev}</span>
                        <span className="font-medium">{report.risk_summary[sev] ?? 0}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded border border-slate-800 p-3">
                    <div className="text-xs text-slate-500">Overall Score</div>
                    <div className="text-2xl font-semibold">{report.overall_score}/100</div>
                  </div>
                  {report.analysis_status === "stale" && (
                    <p className="mt-3 rounded border border-amber-900 bg-amber-950/30 p-2 text-xs text-amber-300">
                      This contract was edited since the last analysis — re-analyze for current results.
                    </p>
                  )}
                </div>
                <div className="col-span-2">
                  <h2 className="text-lg font-medium">Executive Summary</h2>
                  <p className="mt-2 text-sm text-slate-300">{report.executive_summary}</p>
                </div>
              </div>
            )}

            {tab === "Clauses" && (
              <div className="grid grid-cols-3 gap-6">
                <ul className="col-span-1 space-y-1 text-sm">
                  {clauses.map((c) => (
                    <li key={c.id}>
                      <button
                        onClick={() => setSelectedClauseId(c.id)}
                        className={`w-full rounded border px-2 py-1.5 text-left ${
                          selectedClauseId === c.id ? "border-slate-500 bg-slate-900" : "border-slate-800 hover:bg-slate-900"
                        }`}
                      >
                        {c.clause_number ?? "—"} · {c.clause_type}
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="col-span-2">
                  {selectedClause ? (
                    <div className="rounded border border-slate-700 bg-slate-900 p-3 text-sm text-slate-300">
                      <div className="text-xs text-slate-500">
                        Clause {selectedClause.clause_number} · confidence {Math.round(selectedClause.confidence * 100)}%
                      </div>
                      <p className="mt-2 whitespace-pre-wrap">{selectedClause.original_text}</p>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-500">Select a clause to view its text.</p>
                  )}
                </div>
              </div>
            )}

            {tab === "Risks" && (
              <div className="space-y-3">
                <h2 className="text-lg font-medium">Risks &amp; Missing Clauses</h2>
                {report.risks.map((risk) => (
                  <div key={risk.id} className={`rounded border p-3 text-sm ${SEVERITY_COLOR[risk.severity]}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold uppercase">{risk.severity}</span>
                      <StatusBadge status={risk.verification_status} />
                    </div>
                    <div className="mt-1 font-medium text-slate-100">{risk.title}</div>
                    <div className="mt-1 text-slate-300">{risk.description}</div>
                    {risk.why_it_matters && <div className="mt-1 text-slate-400">Почему это важно: {risk.why_it_matters}</div>}
                    {risk.legal_basis && <div className="mt-1 text-slate-400">Правовое основание: {risk.legal_basis}</div>}
                    {risk.recommendation && (
                      <div className="mt-1 text-slate-400">
                        Рекомендация ({risk.recommendation.action}): {risk.recommendation.reason}
                      </div>
                    )}
                    {risk.alternative_clause && (
                      <div className="mt-2 rounded bg-slate-950/60 p-2 text-slate-300">
                        <div className="text-xs text-slate-500">Предлагаемая редакция:</div>
                        {risk.alternative_clause.proposed_text}
                      </div>
                    )}
                    <div className="mt-2 flex gap-2">
                      {risk.clause_id && (
                        <button
                          onClick={() => {
                            setTab("Clauses");
                            setSelectedClauseId(risk.clause_id);
                          }}
                          className="rounded border border-slate-700 px-2 py-1 text-xs hover:bg-slate-800"
                        >
                          View Clause
                        </button>
                      )}
                      {risk.citations.length > 0 && (
                        <span className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-400">
                          {risk.citations.join(", ")}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
                {missingClauseRisks.length === 0 && (
                  <p className="text-xs text-slate-500">No missing-clause coverage gaps flagged.</p>
                )}
              </div>
            )}

            {tab === "Research" && (
              <div className="rounded border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-400">
                Risk verification is backed by the Legal Research Engine internally — each risk&apos;s citations above
                come from verified research, but individual per-risk research reports aren&apos;t separately browsable
                yet. Use the Legal Research workspace to run new research on this contract&apos;s subject matter.
              </div>
            )}

            {tab === "Redline" && (
              <div className="space-y-4">
                <p className="text-xs text-slate-500">
                  AI proposes changes below; nothing is applied to the document automatically. Accept or reject each
                  change explicitly.
                </p>
                {redline === null && <p className="text-sm text-slate-500">Loading…</p>}
                {redline?.length === 0 && <p className="text-sm text-slate-500">No redline changes proposed.</p>}
                {redline?.map((change) => (
                  <div key={change.id} className="rounded border border-slate-800 p-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500">{change.reason}</span>
                      <span
                        className={`rounded px-2 py-0.5 text-[10px] uppercase ${
                          change.review_status === "accepted"
                            ? "bg-emerald-900 text-emerald-300"
                            : change.review_status === "rejected"
                              ? "bg-red-900 text-red-300"
                              : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {change.review_status}
                      </span>
                    </div>
                    <div className="mt-2 rounded bg-slate-950/60 p-2">
                      <DiffView diffOps={change.diff_ops} />
                    </div>
                    {change.review_status === "proposed" && (
                      <div className="mt-2 flex gap-2">
                        <button
                          onClick={() => handleDecision(change.id, "accepted")}
                          disabled={decidingId === change.id}
                          className="rounded border border-emerald-800 px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-950/40 disabled:opacity-50"
                        >
                          Accept
                        </button>
                        <button
                          onClick={() => handleDecision(change.id, "rejected")}
                          disabled={decidingId === change.id}
                          className="rounded border border-red-800 px-2 py-1 text-xs text-red-300 hover:bg-red-950/40 disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {tab === "Versions" && (
              <div>
                <ul className="space-y-2 text-sm">
                  {versions.map((v) => (
                    <li key={v.id} className="flex items-center justify-between rounded border border-slate-800 p-3">
                      <span className="text-slate-300">
                        v{v.version_number} {v.is_current && <span className="text-emerald-400">(current)</span>}
                      </span>
                      <span className="text-xs text-slate-500">{new Date(v.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
                {versions.length < 2 && (
                  <p className="mt-3 text-xs text-slate-500">
                    Only one version exists — version comparison becomes available once the contract is re-uploaded.
                  </p>
                )}
              </div>
            )}

            {tab === "Audit" && (
              <div className="rounded border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-500">
                Per-contract audit trail UI is not implemented yet — analysis and redline-decision events are logged
                server-side (structured logs), not yet exposed through a dedicated API.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
