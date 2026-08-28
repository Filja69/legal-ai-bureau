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
  getCaseLegalTheories,
  getCaseMasterReport,
  getCaseResultSummary,
  getCaseTimeline,
  listCaseContradictions,
  listCaseDocuments,
  listCaseFacts,
} from "@/api/litigation";
import { listResearchReports } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import type { CaseDocumentRole, LegalTheory } from "@/types/litigation";
import { Badge, Button, Card, CardHeader, Notice, PageHeader, RankedItem, RankedList, TableWrap, Td, Th, Timeline, TimelineRow, toneForSeverity } from "@/components/ui";
import { MasterReportSection } from "./MasterReportSection";
import { LegalTheorySection } from "./LegalTheorySection";

const TABS = ["Overview", "Documents", "Facts", "Timeline", "Evidence", "Issues", "Research", "Legal Theories", "Strategy", "Drafts"] as const;
type Tab = (typeof TABS)[number];

// Tabs whose backing engine is explicitly out of scope this phase (brief §58's
// stop condition — claims/defenses/issue-tree/opponent-model/strategy/drafts).
// We show the tab so the product surface exists, but never fabricate content.
const NOT_YET_AVAILABLE: Partial<Record<Tab, string>> = {
  Issues: "A persisted legal-issue tree is not implemented yet — issue identification only runs inside standalone Legal Research.",
  Strategy: "Opponent modeling, counterarguments, and strategy generation are explicitly out of scope this phase.",
  Drafts: "Draft procedural document generation is explicitly out of scope this phase.",
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
  const [legalTheories, setLegalTheories] = useState<LegalTheory[] | null>(null);
  const [runningLegalTheories, setRunningLegalTheories] = useState(false);
  const [legalTheoriesError, setLegalTheoriesError] = useState<string | null>(null);

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

  // Never triggered automatically — real LegalResearchEngine calls (real LLM
  // usage, real time/cost), run only on this explicit user action.
  async function handleRunLegalTheories() {
    if (!workspaceId) return;
    setRunningLegalTheories(true);
    setLegalTheoriesError(null);
    try {
      const theories = await getCaseLegalTheories(workspaceId, caseId);
      setLegalTheories(theories);
    } catch {
      setLegalTheoriesError("Legal research failed — see server logs.");
    } finally {
      setRunningLegalTheories(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Select a workspace to view this case.</div>;
  }
  if (caseQuery.isLoading) {
    return <div className="p-8 text-sm text-muted">Loading…</div>;
  }
  if (caseQuery.isError || !caseQuery.data) {
    return <div className="p-8 text-sm text-danger">Case not found.</div>;
  }

  const c = caseQuery.data;
  const attachedDocumentIds = new Set((caseDocumentsQuery.data ?? []).map((d) => d.document_id));
  const readyUnattachedDocuments = (allDocumentsQuery.data ?? []).filter(
    (d) => d.status === "ready" && !attachedDocumentIds.has(d.id)
  );
  const report = masterReportQuery.data;
  const summary = resultSummaryQuery.data;

  const subtitleParts = [c.status, c.client_name && `Клиент: ${c.client_name}`, c.counterparty_name && `Контрагент: ${c.counterparty_name}`, c.matter_type]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="mx-auto max-w-[1400px] p-4 sm:p-7">
      <PageHeader
        title={c.title}
        description={subtitleParts}
        actions={
          <Button variant="primary" onClick={handleAnalyze} disabled={analyzing}>
            {analyzing ? "Analyzing…" : "Run Full Analysis"}
          </Button>
        }
      />
      {error && (
        <div className="mb-4">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}

      <div className="mb-6 flex w-fit gap-1 overflow-x-auto rounded-xl border border-line bg-panel-muted p-1 text-sm">
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

      <div>
        {tab === "Overview" && (
          <div className="space-y-5">
            <div className="text-xs font-bold uppercase tracking-wide text-muted">Master Case Report — 30-second Case Position</div>

            {report && <MasterReportSection report={report} caseStatus={c.status} documentCount={caseDocumentsQuery.data?.length} />}

            {summary && (
              <Card>
                <CardHeader title="Главный вывод по делу" />
                <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs text-muted">Ключевое противоречие</dt>
                    <dd className="mt-0.5 text-sm text-ink">{summary.key_findings[0]?.statement ?? "Не выявлено на текущих данных."}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Общая сумма платежей</dt>
                    <dd className="mt-0.5 text-sm text-ink">
                      {summary.money_flow.total_amount} ({summary.money_flow.transaction_count} платеж(ей))
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Критически недостающий документ</dt>
                    <dd className="mt-0.5 text-sm text-ink">{summary.missing_critical_evidence[0]?.description ?? "Не выявлено."}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Следующее действие</dt>
                    <dd className="mt-0.5 text-sm text-ink">{summary.next_best_actions[0]?.action ?? "Недостаточно данных для рекомендации."}</dd>
                  </div>
                </dl>
                {summary.legal_kb_warning && (
                  <p className="mt-3 border-t border-line pt-3 text-xs text-amber-700">{summary.legal_kb_warning}</p>
                )}
              </Card>
            )}

            {summary && summary.party_relationship_findings.length > 0 && (
              <Card>
                <CardHeader title="Связи сторон и обстоятельства, требующие проверки" />
                <div className="space-y-3.5">
                  {summary.party_relationship_findings.map((f, i) => (
                    <div key={i} className="border-t border-line pt-3.5 first:border-t-0 first:pt-0">
                      <div className="text-sm text-ink">
                        <span className="font-semibold">{f.subject_name}</span> — {f.relationship_type} «{f.related_party_name}»
                      </div>
                      <div className="mt-1 text-xs text-muted">{f.timing_note}</div>
                      <div className="mt-1 text-xs text-slate-600">{f.why_it_may_matter}</div>
                      {f.what_is_still_needed.length > 0 && (
                        <div className="mt-1 text-xs text-muted">Требует проверки: {f.what_is_still_needed.join("; ")}</div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {summary && summary.next_best_actions.length > 0 && (
              <Card>
                <CardHeader title="План дальнейших действий" description="Ранжировано по приоритету." />
                <RankedList>
                  {summary.next_best_actions.map((a) => (
                    <RankedItem key={a.priority} rank={a.priority} title={a.action}>
                      {a.why}
                    </RankedItem>
                  ))}
                </RankedList>
              </Card>
            )}

            <Card>
              <CardHeader title="Детали дела" />
              <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted">Status</dt>
                  <dd className="mt-0.5 text-ink">{c.status}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Matter type</dt>
                  <dd className="mt-0.5 text-ink">{c.matter_type ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Client</dt>
                  <dd className="mt-0.5 text-ink">{c.client_name ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Counterparty</dt>
                  <dd className="mt-0.5 text-ink">{c.counterparty_name ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted">Documents attached</dt>
                  <dd className="mt-0.5 text-ink">{caseDocumentsQuery.data?.length ?? "—"}</dd>
                </div>
              </dl>
            </Card>
          </div>
        )}

        {tab === "Documents" && (
          <div className="space-y-4">
            <Card>
              <div className="flex flex-col gap-2 sm:flex-row">
                <select
                  value={selectedDocumentId}
                  onChange={(e) => setSelectedDocumentId(e.target.value)}
                  className="flex-1 rounded-lg border border-line bg-white p-2 text-sm text-ink"
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
                  className="rounded-lg border border-line bg-white p-2 text-sm text-ink"
                >
                  {DOCUMENT_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                <Button variant="primary" onClick={handleAttachDocument} disabled={attaching || !selectedDocumentId}>
                  {attaching ? "Attaching…" : "Attach"}
                </Button>
              </div>
              {readyUnattachedDocuments.length === 0 && allDocumentsQuery.data && (
                <p className="mt-2 text-xs text-muted">
                  No ready, unattached documents.{" "}
                  <Link href="/documents" className="text-brand hover:underline">
                    Upload one →
                  </Link>
                </p>
              )}
            </Card>
            <div className="space-y-2">
              {caseDocumentsQuery.data?.map((cd) => (
                <Card key={cd.id} className="flex items-center justify-between p-3.5">
                  <Link href={`/documents/${cd.document_id}`} className="font-medium text-ink hover:underline">
                    {cd.document_title}
                  </Link>
                  <Badge tone="gray">{cd.role}</Badge>
                </Card>
              ))}
              {caseDocumentsQuery.data?.length === 0 && <p className="text-sm text-muted">No documents attached yet.</p>}
            </div>
          </div>
        )}

        {tab === "Facts" && (
          <div className="space-y-4">
            <Button variant="primary" onClick={handleExtractFacts} disabled={extracting}>
              {extracting ? "Extracting…" : "Extract Facts from Attached Documents"}
            </Button>
            <p className="text-xs text-muted">
              Only deterministic date/amount/party facts extracted from attached, READY documents — every fact links back to
              the exact document, page, and excerpt it came from.
            </p>
            {factsQuery.data?.length === 0 && <p className="text-sm text-muted">No facts extracted yet.</p>}
            <div className="space-y-2.5">
              {factsQuery.data?.map((fact) => (
                <Card key={fact.id}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm text-ink">{fact.statement}</span>
                    <Badge tone={toneForSeverity(fact.status)}>{fact.status}</Badge>
                  </div>
                  {fact.evidence.map((e, i) => (
                    <div key={i} className="mt-2 rounded-lg bg-panel-muted p-2.5 text-xs text-slate-600">
                      <Link href={`/documents/${e.document_id}`} className="text-brand hover:underline">
                        {e.document_title}
                      </Link>
                      {e.page_number && ` · стр. ${e.page_number}`}
                      <div className="mt-1">{e.excerpt}</div>
                    </div>
                  ))}
                </Card>
              ))}
            </div>
          </div>
        )}

        {tab === "Timeline" && (
          <Card>
            {timelineQuery.data?.length === 0 && <p className="text-sm text-muted">No timeline yet — extract facts and run analysis first.</p>}
            <Timeline>
              {timelineQuery.data?.map((event, i) => (
                <TimelineRow key={event.id} date={event.event_date ?? "Date unknown"} isLast={i === (timelineQuery.data?.length ?? 0) - 1}>
                  <div className="mb-1 flex items-center gap-2">
                    <Badge tone="gray">{event.date_type}</Badge>
                    {event.event_type && <span className="text-xs text-muted">[{event.event_type}]</span>}
                  </div>
                  <div className="text-sm text-ink">{event.description}</div>
                </TimelineRow>
              ))}
            </Timeline>
          </Card>
        )}

        {tab === "Evidence" && (
          <div className="space-y-5">
            <Card>
              <CardHeader title="Evidence Matrix" />
              <TableWrap>
                <thead>
                  <tr>
                    <Th>Fact</Th>
                    <Th>Strength</Th>
                    <Th>Reasons</Th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceQuery.data?.map((row, i) => (
                    <tr key={i}>
                      <Td className="text-ink">{row.fact_statement}</Td>
                      <Td>
                        <Badge tone={toneForSeverity(row.strength)}>{row.strength}</Badge>
                      </Td>
                      <Td className="text-xs text-muted">{row.reasons.join("; ")}</Td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              {evidenceQuery.data?.length === 0 && <p className="mt-2 text-sm text-muted">No facts to evaluate yet.</p>}
            </Card>

            <Card>
              <CardHeader title="Contradictions" />
              {contradictionsQuery.data?.length === 0 && <p className="text-sm text-muted">None detected.</p>}
              <div className="space-y-2.5">
                {contradictionsQuery.data?.map((con) => (
                  <div key={con.id} className="rounded-xl border border-red-200 bg-danger-soft p-3.5">
                    <Badge tone="red">{con.contradiction_type.replace("_", " ")}</Badge>
                    <div className="mt-1.5 text-sm text-ink">{con.description}</div>
                    <div className="mt-1 text-xs text-muted">
                      &quot;{con.fact_a_statement}&quot; vs &quot;{con.fact_b_statement}&quot;
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {tab === "Research" && (
          <Card>
            {researchQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {researchQuery.data?.items.length === 0 && <p className="text-sm text-muted">No research linked to this case yet.</p>}
            <div className="space-y-2">
              {researchQuery.data?.items.map((r) => (
                <div key={r.id} className="rounded-xl border border-line p-3.5 text-sm">
                  <Link href={`/research/${r.id}`} className="font-medium text-ink hover:underline">
                    {r.question}
                  </Link>
                  <div className="mt-0.5 text-muted">{r.confidence} confidence</div>
                </div>
              ))}
            </div>
            <Link href="/research" className="mt-3 inline-block text-xs text-brand hover:underline">
              Run new research for this case →
            </Link>
          </Card>
        )}

        {tab === "Legal Theories" && (
          <div className="space-y-4">
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-muted">
                  Запускает независимую правовую проверку по фактам дела (реальные вызовы LLM и Базы Знаний, может занять
                  несколько минут). Не запускается автоматически.
                </p>
                <Button variant="primary" onClick={handleRunLegalTheories} disabled={runningLegalTheories}>
                  {runningLegalTheories ? "Анализируем…" : "Запустить правовой анализ"}
                </Button>
              </div>
            </Card>
            {legalTheoriesError && <Notice tone="danger">{legalTheoriesError}</Notice>}
            {legalTheories && <LegalTheorySection theories={legalTheories} />}
          </div>
        )}

        {NOT_YET_AVAILABLE[tab] && <Notice tone="info">{NOT_YET_AVAILABLE[tab]}</Notice>}
      </div>
    </div>
  );
}
