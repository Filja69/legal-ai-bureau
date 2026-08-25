"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContract } from "@/api/contracts";
import {
  analyzeDocument,
  askDocument,
  deleteDocument,
  getDocument,
  getDocumentText,
  reprocessDocument,
} from "@/api/documents";
import { useAuth } from "@/hooks/useAuth";
import type { DocumentAnalyzeResponse, DocumentCitation } from "@/types/document";
import { Badge, Button, Card, CardHeader, Notice } from "@/components/ui";
import { DocumentStatusBadge } from "./DocumentStatusBadge";

const TABS = ["Overview", "Content", "Analysis", "Ask", "Citations"] as const;
type Tab = (typeof TABS)[number];

export function DocumentDetailView({ documentId }: { documentId: string }) {
  const { workspaceId } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("Overview");
  const [retrying, setRetrying] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [askHistory, setAskHistory] = useState<
    { question: string; answer: string; citations: DocumentCitation[]; answerMethod: "extractive" | "llm" }[]
  >([]);
  const [analysis, setAnalysis] = useState<DocumentAnalyzeResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [creatingContract, setCreatingContract] = useState(false);
  const [createContractError, setCreateContractError] = useState<string | null>(null);

  const documentQuery = useQuery({
    queryKey: ["document", workspaceId, documentId],
    queryFn: () => getDocument(workspaceId!, documentId),
    enabled: !!workspaceId,
    retry: false,
  });

  const contentQuery = useQuery({
    queryKey: ["document", workspaceId, documentId, "text"],
    queryFn: () => getDocumentText(workspaceId!, documentId),
    enabled: !!workspaceId && tab === "Content" && documentQuery.data?.status === "ready",
    retry: false,
  });

  async function handleRetry() {
    if (!workspaceId) return;
    setRetrying(true);
    try {
      await reprocessDocument(workspaceId, documentId);
      await queryClient.invalidateQueries({ queryKey: ["document", workspaceId, documentId] });
    } finally {
      setRetrying(false);
    }
  }

  async function handleDelete() {
    if (!workspaceId) return;
    setDeleting(true);
    try {
      await deleteDocument(workspaceId, documentId);
      router.push("/documents");
    } finally {
      setDeleting(false);
    }
  }

  async function handleAsk() {
    if (!workspaceId || !question.trim()) return;
    setAsking(true);
    setAskError(null);
    try {
      const result = await askDocument(workspaceId, documentId, question);
      setAskHistory((prev) => [
        { question, answer: result.answer, citations: result.citations, answerMethod: result.answer_method },
        ...prev,
      ]);
      if (result.status === "insufficient_document_evidence") {
        setAskError("Insufficient document evidence to answer this question — nothing was fabricated.");
      }
      setQuestion("");
    } catch {
      setAskError("Ask failed.");
    } finally {
      setAsking(false);
    }
  }

  async function handleCreateContract() {
    if (!workspaceId) return;
    const doc = documentQuery.data;
    if (!doc) return;
    setCreatingContract(true);
    setCreateContractError(null);
    try {
      const contract = await createContract(workspaceId, {
        title: doc.title,
        contract_type: "unknown",
        document_id: doc.id,
      });
      router.push(`/contracts/${contract.id}`);
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setCreateContractError(detail ?? "Не удалось отправить договор на проверку — попробуйте ещё раз.");
    } finally {
      setCreatingContract(false);
    }
  }

  async function handleAnalyze() {
    if (!workspaceId) return;
    setAnalyzing(true);
    setAnalyzeError(null);
    try {
      const result = await analyzeDocument(workspaceId, documentId);
      setAnalysis(result);
      if (result.status === "insufficient_document_evidence") {
        setAnalyzeError("Insufficient document evidence to analyze.");
      }
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setAnalyzeError(detail ?? "Analysis failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Select a workspace to view this document.</div>;
  }
  if (documentQuery.isLoading) {
    return <div className="p-8 text-sm text-muted">Loading…</div>;
  }
  if (documentQuery.isError || !documentQuery.data) {
    return <div className="p-8 text-sm text-danger">Document not found.</div>;
  }

  const doc = documentQuery.data;
  const allCitations = askHistory.flatMap((h) => h.citations);

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold text-ink">{doc.title}</h1>
        <DocumentStatusBadge status={doc.status} />
      </div>
      <p className="mt-1 text-sm text-muted">
        {doc.media_type} · {doc.original_filename}
      </p>

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
          <Card className="space-y-4">
            {doc.processing_error && <Notice tone="warning">{doc.processing_error}</Notice>}
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <dt className="text-muted">Status</dt>
              <dd className="text-ink">{doc.status}</dd>
              <dt className="text-muted">SHA-256</dt>
              <dd className="break-all text-ink">{doc.sha256 ?? "—"}</dd>
              <dt className="text-muted">Extractor</dt>
              <dd className="text-ink">{doc.doc_metadata.extractor ?? "—"}</dd>
              <dt className="text-muted">Pages</dt>
              <dd className="text-ink">{doc.doc_metadata.page_count ?? "—"}</dd>
              <dt className="text-muted">Chunks indexed</dt>
              <dd className="text-ink">{doc.doc_metadata.chunk_count ?? "—"}</dd>
              <dt className="text-muted">Structure detected</dt>
              <dd className="text-ink">{doc.doc_metadata.used_structure_detection ? "Yes" : "No (plain-text fallback)"}</dd>
            </dl>
            {doc.doc_metadata.warnings && doc.doc_metadata.warnings.length > 0 && (
              <ul className="list-inside list-disc text-xs text-muted">
                {doc.doc_metadata.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              {doc.status === "ready" && (
                <Button variant="primary" onClick={handleCreateContract} disabled={creatingContract}>
                  {creatingContract ? "Отправка…" : "Отправить на проверку договора"}
                </Button>
              )}
              {(doc.status === "failed" || doc.status === "ocr_required") && (
                <Button onClick={handleRetry} disabled={retrying}>
                  {retrying ? "Retrying…" : "Retry Processing"}
                </Button>
              )}
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-lg border border-red-200 px-3.5 py-2 text-sm font-semibold text-danger hover:bg-danger-soft disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
            {createContractError && <p className="text-sm text-danger">{createContractError}</p>}
          </Card>
        )}

        {tab === "Content" && (
          <Card>
            {doc.status !== "ready" && (
              <p className="text-sm text-muted">
                Extracted text is only available once the document is READY (current status: {doc.status}).
              </p>
            )}
            {doc.status === "ready" && contentQuery.isLoading && <p className="text-sm text-muted">Loading…</p>}
            {doc.status === "ready" && contentQuery.data && (
              <pre className="whitespace-pre-wrap rounded-lg border border-line bg-panel-muted p-4 text-sm text-slate-700">
                {contentQuery.data}
              </pre>
            )}
          </Card>
        )}

        {tab === "Analysis" && (
          <div className="space-y-5">
            <Card>
              {doc.status !== "ready" ? (
                <p className="text-sm text-muted">Document must be READY to analyze.</p>
              ) : (
                <Button variant="primary" onClick={handleAnalyze} disabled={analyzing}>
                  {analyzing ? "Analyzing…" : "Run Analysis"}
                </Button>
              )}
              {analyzeError && <p className="mt-2 text-sm text-warning">{analyzeError}</p>}
            </Card>
            {analysis && (
              <div className="space-y-4">
                {analysis.document_type_extracted && (
                  <Card>
                    <p className="text-sm text-ink">
                      <span className="text-muted">Document type (EXTRACTED):</span> {analysis.document_type_extracted}
                    </p>
                  </Card>
                )}
                <FactSection title="Dates (EXTRACTED)" facts={analysis.extracted_dates} />
                <FactSection title="Amounts (EXTRACTED)" facts={analysis.extracted_amounts} />
                <FactSection title="Parties (EXTRACTED)" facts={analysis.extracted_parties} />
                <TextListSection title="Obligations (INFERRED)" items={analysis.inferred_obligations} />
                <TextListSection title="Risks (INFERRED)" items={analysis.inferred_risks} />
                <TextListSection title="Missing Information (INFERRED)" items={analysis.inferred_missing_information} />
              </div>
            )}
          </div>
        )}

        {tab === "Ask" && (
          <div className="space-y-4">
            <Card>
              {doc.status !== "ready" ? (
                <p className="text-sm text-muted">Document must be READY to ask questions.</p>
              ) : (
                <div className="flex gap-2">
                  <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="Ask about this document"
                    className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink"
                  />
                  <Button variant="primary" onClick={handleAsk} disabled={asking || !question.trim()}>
                    {asking ? "Asking…" : "Submit Question"}
                  </Button>
                </div>
              )}
              {askError && <p className="mt-2 text-sm text-warning">{askError}</p>}
            </Card>

            <div className="space-y-3">
              {askHistory.map((h, i) => (
                <Card key={i}>
                  <div className="text-xs text-muted">Q: {h.question}</div>
                  {h.answer ? (
                    <>
                      <div className="mt-1.5 flex items-center gap-2">
                        <span className="text-sm text-ink">{h.answer}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                            h.answerMethod === "extractive" ? "bg-success-soft text-success" : "bg-slate-100 text-slate-600"
                          }`}
                          title={
                            h.answerMethod === "extractive"
                              ? "Deterministic regex match — no LLM was called for this answer"
                              : "LLM-reasoned, evidence-gated answer"
                          }
                        >
                          {h.answerMethod === "extractive" ? "Extracted" : "AI-reasoned"}
                        </span>
                      </div>
                      {h.citations.length > 0 && (
                        <ul className="mt-2 space-y-1.5">
                          {h.citations.map((c, j) => (
                            <li key={j} className="rounded-lg bg-panel-muted p-2.5 text-xs text-slate-600">
                              <div className="font-medium text-slate-700">{c.label}</div>
                              <div className="mt-1">{c.excerpt}</div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : (
                    <div className="mt-1.5 text-sm text-warning">Insufficient document evidence to answer.</div>
                  )}
                </Card>
              ))}
            </div>
          </div>
        )}

        {tab === "Citations" && (
          <div>
            {allCitations.length === 0 && (
              <p className="text-sm text-muted">No citations yet — citations appear here as you ask questions in the Ask tab.</p>
            )}
            <div className="space-y-2.5">
              {allCitations.map((c, i) => (
                <Card key={i}>
                  <div className="flex items-center gap-2">
                    <Badge tone="green">DOCUMENT EVIDENCE</Badge>
                    <span className="font-medium text-ink">{c.label}</span>
                  </div>
                  <div className="mt-1.5 text-sm text-slate-600">{c.excerpt}</div>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FactSection({ title, facts }: { title: string; facts: { value: string; provenance: string }[] }) {
  if (facts.length === 0) return null;
  return (
    <Card>
      <CardHeader title={title} />
      <ul className="space-y-1.5 text-sm">
        {facts.map((f, i) => (
          <li key={i} className="flex justify-between rounded-lg border border-line px-2.5 py-1.5">
            <span className="text-ink">{f.value}</span>
            <span className="text-xs text-muted">{f.provenance}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function TextListSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Card>
      <CardHeader title={title} />
      <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </Card>
  );
}
