"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { getCase } from "@/api/legal";
import { listDocuments } from "@/api/documents";
import {
  analyzeCase,
  attachCaseDocument,
  extractCaseFacts,
  getCaseEvidenceMatrix,
  getCaseMasterReport,
  getCaseResultSummary,
  getCaseTimeline,
  listCaseContradictions,
  listCaseDocuments,
  listCaseFacts,
} from "@/api/litigation";
import { listResearchReports } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import type { CaseDocumentRole, FactStatus } from "@/types/litigation";

const TABS = ["Overview", "Documents", "Facts", "Timeline", "Evidence", "Issues", "Research", "Strategy", "Drafts"] as const;
type Tab = (typeof TABS)[number];

// Tabs whose backing engine is explicitly out of scope this phase (brief §58's
// stop condition — claims/defenses/issue-tree/opponent-model/strategy/drafts).
// We show the tab so the product surface exists, but never fabricate content.
const NOT_YET_AVAILABLE: Partial<Record<Tab, string>> = {
  Issues: "A persisted legal-issue tree is not implemented yet — issue identification only runs inside standalone Legal Research.",
  Strategy: "Opponent modeling, counterarguments, and strategy generation are explicitly out of scope this phase.",
  Drafts: "Draft procedural document generation is explicitly out of scope this phase.",
};

const FACT_STATUS_STYLE: Record<FactStatus, string> = {
  supported: "bg-emerald-950 text-emerald-300 border border-emerald-900",
  disputed: "bg-amber-950 text-amber-300 border border-amber-900",
  contradicted: "bg-red-950 text-red-300 border border-red-900",
  inferred: "bg-indigo-950 text-indigo-300 border border-indigo-900",
  asserted: "bg-slate-800 text-slate-300 border border-slate-700",
  unknown: "bg-slate-800 text-slate-400 border border-slate-700 border-dashed",
};

const EVIDENCE_STRENGTH_STYLE: Record<string, string> = {
  strong: "bg-emerald-950 text-emerald-300 border border-emerald-900",
  moderate: "bg-slate-800 text-slate-300 border border-slate-700",
  weak: "bg-amber-950 text-amber-300 border border-amber-900",
  conflicted: "bg-red-950 text-red-300 border border-red-900",
  insufficient: "bg-slate-800 text-slate-500 border border-slate-700 border-dashed",
};

const DOCUMENT_ROLES: CaseDocumentRole[] = [
  "contract", "addendum", "invoice", "act", "correspondence", "claim", "response",
  "court_filing", "court_decision", "expert_report", "payment_document", "other",
];

export function CaseDetailView({ caseId }: { caseId: string }) {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedRole, setSelectedRole] = useState<CaseDocumentRole>("other");
  const [attaching, setAttaching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);

  const caseQuery = useQuery({
    queryKey: ["case", workspaceId, caseId],
    queryFn: () => getCase(workspaceId!, caseId),
    enabled: !!workspaceId,
    retry: false,
  });

  const researchQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "research"],
    queryFn: () => listResearchReports(workspaceId!, { caseId, limit: 50 }),
    enabled: !!workspaceId && tab === "Research",
  });

  const caseDocumentsQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "documents"],
    queryFn: () => listCaseDocuments(workspaceId!, caseId),
    enabled: !!workspaceId,
  });

  const resultSummaryQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "result-summary"],
    queryFn: () => getCaseResultSummary(workspaceId!, caseId),
    enabled: !!workspaceId && tab === "Overview",
  });

  const masterReportQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "master-report"],
    queryFn: () => getCaseMasterReport(workspaceId!, caseId),
    enabled: !!workspaceId && tab === "Overview",
  });

  const allDocumentsQuery = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: () => listDocuments(workspaceId!),
    enabled: !!workspaceId && tab === "Documents",
  });

  const factsQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "facts"],
    queryFn: () => listCaseFacts(workspaceId!, caseId),
    enabled: !!workspaceId && tab === "Facts",
  });

  const timelineQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "timeline"],
    queryFn: () => getCaseTimeline(workspaceId!, caseId),
    enabled: !!workspaceId && tab === "Timeline",
  });

  const evidenceQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "evidence-matrix"],
    queryFn: () => getCaseEvidenceMatrix(workspaceId!, caseId),
    enabled: !!workspaceId && tab === "Evidence",
  });

  const contradictionsQuery = useQuery({
    queryKey: ["case", workspaceId, caseId, "contradictions"],
    queryFn: () => listCaseContradictions(workspaceId!, caseId),
    enabled: !!workspaceId && tab === "Evidence",
  });

  async function handleAttachDocument() {
    if (!workspaceId || !selectedDocumentId) return;
    setAttaching(true);
    setError(null);
    try {
      await attachCaseDocument(workspaceId, caseId, selectedDocumentId, selectedRole);
      setSelectedDocumentId("");
      await queryClient.invalidateQueries({ queryKey: ["case", workspaceId, caseId, "documents"] });
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? "Could not attach document.");
    } finally {
      setAttaching(false);
    }
  }

  async function handleExtractFacts() {
    if (!workspaceId) return;
    setExtracting(true);
    setError(null);
    try {
      await extractCaseFacts(workspaceId, caseId);
      await queryClient.invalidateQueries({ queryKey: ["case", workspaceId, caseId, "facts"] });
    } catch {
      setError("Fact extraction failed.");
    } finally {
      setExtracting(false);
    }
  }

  async function handleAnalyze() {
    if (!workspaceId) return;
    setAnalyzing(true);
    setError(null);
    try {
      await analyzeCase(workspaceId, caseId);
      await queryClient.invalidateQueries({ queryKey: ["case", workspaceId, caseId] });
    } catch {
      setError("Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-slate-500">Select a workspace to view this case.</div>;
  }
  if (caseQuery.isLoading) {
    return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  }
  if (caseQuery.isError || !caseQuery.data) {
    return <div className="p-8 text-sm text-red-400">Case not found.</div>;
  }

  const c = caseQuery.data;
  const attachedDocumentIds = new Set((caseDocumentsQuery.data ?? []).map((d) => d.document_id));
  const readyUnattachedDocuments = (allDocumentsQuery.data ?? []).filter(
    (d) => d.status === "ready" && !attachedDocumentIds.has(d.id)
  );

  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{c.title}</h1>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="rounded bg-slate-700 px-3 py-1.5 text-xs font-medium hover:bg-slate-600 disabled:opacity-50"
        >
          {analyzing ? "Analyzing…" : "Run Full Analysis"}
        </button>
      </div>
      <p className="mt-1 text-sm text-slate-400">
        {c.status}
        {c.client_name && ` · Client: ${c.client_name}`}
        {c.counterparty_name && ` · Counterparty: ${c.counterparty_name}`}
        {c.matter_type && ` · ${c.matter_type}`}
      </p>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

      <div className="mt-6 flex gap-1 overflow-x-auto border-b border-slate-800 text-sm">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`shrink-0 px-3 py-2 ${
              tab === t ? "border-b-2 border-slate-200 text-slate-100" : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === "Overview" && (
          <div className="space-y-6">
            {masterReportQuery.data && (
              <div className="rounded border border-indigo-900 bg-indigo-950/20 p-4 text-sm">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-indigo-300">Master Case Report — 30-second Case Position</h2>
                <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-slate-500">Money at stake</dt>
                    <dd className="text-slate-200">{masterReportQuery.data.one_pager.money_at_stake}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Strongest point</dt>
                    <dd className="text-slate-200">{masterReportQuery.data.one_pager.strongest_point ?? "Not identified yet."}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Biggest risk</dt>
                    <dd className="text-slate-200">{masterReportQuery.data.one_pager.biggest_risk ?? "Not identified yet."}</dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Next best action</dt>
                    <dd className="text-slate-200">{masterReportQuery.data.one_pager.next_best_action ?? "Insufficient data for a recommendation."}</dd>
                  </div>
                </dl>

                {masterReportQuery.data.one_pager.missing_p0_evidence.length > 0 && (
                  <div className="mt-3 border-t border-indigo-900 pt-3 text-xs text-amber-400">
                    Missing evidence: {masterReportQuery.data.one_pager.missing_p0_evidence.slice(0, 3).join("; ")}
                  </div>
                )}

                {masterReportQuery.data.findings.length > 0 && (
                  <div className="mt-4">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Top findings</h3>
                    <ul className="mt-2 space-y-3">
                      {masterReportQuery.data.findings.slice(0, 5).map((f) => (
                        <li key={f.id} className="border-t border-indigo-900/60 pt-2 first:border-t-0 first:pt-0">
                          <div className="flex items-center gap-2">
                            <span className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-300">
                              {f.strength}
                            </span>
                            <span className="text-slate-200">{f.title}</span>
                          </div>
                          <div className="mt-1 text-xs text-slate-400">{f.statement}</div>
                          {f.caveat && <div className="mt-1 text-xs text-slate-500">Caveat: {f.caveat}</div>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {masterReportQuery.data.legal_kb_warning && (
                  <p className="mt-3 border-t border-indigo-900 pt-3 text-xs text-amber-400">{masterReportQuery.data.legal_kb_warning}</p>
                )}
              </div>
            )}

            {resultSummaryQuery.data && (
              <div className="rounded border border-slate-800 bg-slate-900/50 p-4 text-sm">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Главный вывод по делу</h2>
                <dl className="mt-3 space-y-2">
                  <div>
                    <dt className="text-slate-500">Ключевое противоречие</dt>
                    <dd className="text-slate-200">
                      {resultSummaryQuery.data.key_findings[0]?.statement ?? "Не выявлено на текущих данных."}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Общая сумма платежей</dt>
                    <dd className="text-slate-200">
                      {resultSummaryQuery.data.money_flow.total_amount} ({resultSummaryQuery.data.money_flow.transaction_count} платеж(ей))
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Критически недостающий документ</dt>
                    <dd className="text-slate-200">
                      {resultSummaryQuery.data.missing_critical_evidence[0]?.description ?? "Не выявлено."}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-slate-500">Следующее действие</dt>
                    <dd className="text-slate-200">
                      {resultSummaryQuery.data.next_best_actions[0]?.action ?? "Недостаточно данных для рекомендации."}
                    </dd>
                  </div>
                </dl>
                {resultSummaryQuery.data.legal_kb_warning && (
                  <p className="mt-3 border-t border-slate-800 pt-3 text-xs text-amber-400">
                    {resultSummaryQuery.data.legal_kb_warning}
                  </p>
                )}
              </div>
            )}

            {resultSummaryQuery.data && resultSummaryQuery.data.party_relationship_findings.length > 0 && (
              <div className="rounded border border-slate-800 bg-slate-900/50 p-4 text-sm">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Связи сторон и обстоятельства, требующие проверки
                </h2>
                <ul className="mt-3 space-y-4">
                  {resultSummaryQuery.data.party_relationship_findings.map((f, i) => (
                    <li key={i} className="border-t border-slate-800 pt-3 first:border-t-0 first:pt-0">
                      <div className="text-slate-200">
                        <span className="font-medium">{f.subject_name}</span> — {f.relationship_type} «{f.related_party_name}»
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{f.timing_note}</div>
                      <div className="mt-1 text-xs text-slate-400">{f.why_it_may_matter}</div>
                      {f.what_is_still_needed.length > 0 && (
                        <div className="mt-1 text-xs text-slate-500">
                          Требует проверки: {f.what_is_still_needed.join("; ")}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-slate-500">Status</dt>
              <dd className="text-slate-200">{c.status}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Matter type</dt>
              <dd className="text-slate-200">{c.matter_type ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Client</dt>
              <dd className="text-slate-200">{c.client_name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Counterparty</dt>
              <dd className="text-slate-200">{c.counterparty_name ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Documents attached</dt>
              <dd className="text-slate-200">{caseDocumentsQuery.data?.length ?? "—"}</dd>
            </div>
            </dl>
          </div>
        )}

        {tab === "Documents" && (
          <div className="space-y-4">
            <div className="flex gap-2">
              <select
                value={selectedDocumentId}
                onChange={(e) => setSelectedDocumentId(e.target.value)}
                className="flex-1 rounded border border-slate-700 bg-slate-900 p-2 text-sm"
              >
                <option value="">Select a ready document…</option>
                {readyUnattachedDocuments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
              <select
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value as CaseDocumentRole)}
                className="rounded border border-slate-700 bg-slate-900 p-2 text-sm"
              >
                {DOCUMENT_ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <button
                onClick={handleAttachDocument}
                disabled={attaching || !selectedDocumentId}
                className="rounded bg-slate-700 px-3 py-1.5 text-sm hover:bg-slate-600 disabled:opacity-50"
              >
                {attaching ? "Attaching…" : "Attach"}
              </button>
            </div>
            {readyUnattachedDocuments.length === 0 && allDocumentsQuery.data && (
              <p className="text-xs text-slate-500">
                No ready, unattached documents. <Link href="/documents" className="hover:underline">Upload one →</Link>
              </p>
            )}
            <ul className="space-y-2">
              {caseDocumentsQuery.data?.map((cd) => (
                <li key={cd.id} className="flex items-center justify-between rounded border border-slate-800 p-3 text-sm">
                  <Link href={`/documents/${cd.document_id}`} className="font-medium text-slate-200 hover:underline">
                    {cd.document_title}
                  </Link>
                  <span className="text-xs text-slate-500">{cd.role}</span>
                </li>
              ))}
              {caseDocumentsQuery.data?.length === 0 && <p className="text-sm text-slate-500">No documents attached yet.</p>}
            </ul>
          </div>
        )}

        {tab === "Facts" && (
          <div className="space-y-4">
            <button
              onClick={handleExtractFacts}
              disabled={extracting}
              className="rounded bg-slate-700 px-3 py-1.5 text-sm hover:bg-slate-600 disabled:opacity-50"
            >
              {extracting ? "Extracting…" : "Extract Facts from Attached Documents"}
            </button>
            <p className="text-xs text-slate-500">
              Only deterministic date/amount/party facts extracted from attached, READY documents — every fact links back to
              the exact document, page, and excerpt it came from.
            </p>
            {factsQuery.data?.length === 0 && <p className="text-sm text-slate-500">No facts extracted yet.</p>}
            <ul className="space-y-2">
              {factsQuery.data?.map((fact) => (
                <li key={fact.id} className="rounded border border-slate-800 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-200">{fact.statement}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${FACT_STATUS_STYLE[fact.status]}`}>
                      {fact.status}
                    </span>
                  </div>
                  {fact.evidence.map((e, i) => (
                    <div key={i} className="mt-1 rounded bg-slate-950/60 p-2 text-xs text-slate-400">
                      <Link href={`/documents/${e.document_id}`} className="text-slate-300 hover:underline">
                        {e.document_title}
                      </Link>
                      {e.page_number && ` · стр. ${e.page_number}`}
                      <div className="mt-1">{e.excerpt}</div>
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === "Timeline" && (
          <div className="space-y-3">
            {timelineQuery.data?.length === 0 && (
              <p className="text-sm text-slate-500">No timeline yet — extract facts and run analysis first.</p>
            )}
            <ul className="relative space-y-4 border-l border-slate-800 pl-4">
              {timelineQuery.data?.map((event) => (
                <li key={event.id}>
                  <div className="text-xs text-slate-500">
                    {event.event_date ?? "Date unknown"}
                    <span className="ml-2 rounded border border-slate-700 px-1.5 py-0.5 text-[10px] uppercase">{event.date_type}</span>
                    {event.event_type && <span className="ml-2 text-slate-600">[{event.event_type}]</span>}
                  </div>
                  <div className="mt-1 text-sm text-slate-200">{event.description}</div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === "Evidence" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-sm font-medium text-slate-300">Evidence Matrix</h2>
              <table className="mt-2 w-full text-left text-sm">
                <thead>
                  <tr className="text-xs text-slate-500">
                    <th className="pb-2">Fact</th>
                    <th className="pb-2">Strength</th>
                    <th className="pb-2">Reasons</th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceQuery.data?.map((row, i) => (
                    <tr key={i} className="border-t border-slate-800">
                      <td className="py-2 pr-4 text-slate-200">{row.fact_statement}</td>
                      <td className="py-2 pr-4">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${EVIDENCE_STRENGTH_STYLE[row.strength]}`}>
                          {row.strength}
                        </span>
                      </td>
                      <td className="py-2 text-xs text-slate-400">{row.reasons.join("; ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {evidenceQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">No facts to evaluate yet.</p>}
            </div>

            <div>
              <h2 className="text-sm font-medium text-slate-300">Contradictions</h2>
              {contradictionsQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">None detected.</p>}
              <ul className="mt-2 space-y-2">
                {contradictionsQuery.data?.map((con) => (
                  <li key={con.id} className="rounded border border-red-900 bg-red-950/30 p-3 text-sm">
                    <div className="text-xs font-semibold uppercase text-red-300">{con.contradiction_type.replace("_", " ")}</div>
                    <div className="mt-1 text-slate-300">{con.description}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      "{con.fact_a_statement}" vs "{con.fact_b_statement}"
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {tab === "Research" && (
          <div>
            {researchQuery.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
            {researchQuery.data?.items.length === 0 && (
              <p className="text-sm text-slate-500">No research linked to this case yet.</p>
            )}
            <ul className="space-y-2">
              {researchQuery.data?.items.map((r) => (
                <li key={r.id} className="rounded border border-slate-800 p-3 text-sm">
                  <Link href={`/research/${r.id}`} className="font-medium text-slate-200 hover:underline">
                    {r.question}
                  </Link>
                  <div className="text-slate-500">{r.confidence} confidence</div>
                </li>
              ))}
            </ul>
            <Link href="/research" className="mt-3 inline-block text-xs text-slate-500 hover:underline">
              Run new research for this case →
            </Link>
          </div>
        )}

        {NOT_YET_AVAILABLE[tab] && (
          <div className="rounded border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-500">
            {NOT_YET_AVAILABLE[tab]}
          </div>
        )}
      </div>
    </div>
  );
}
