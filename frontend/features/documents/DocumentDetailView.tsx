"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
    return <div className="p-8 text-sm text-slate-500">Select a workspace to view this document.</div>;
  }
  if (documentQuery.isLoading) {
    return <div className="p-8 text-sm text-slate-500">Loading…</div>;
  }
  if (documentQuery.isError || !documentQuery.data) {
    return <div className="p-8 text-sm text-red-400">Document not found.</div>;
  }

  const doc = documentQuery.data;
  const allCitations = askHistory.flatMap((h) => h.citations);

  return (
    <div className="mx-auto max-w-4xl p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{doc.title}</h1>
        <DocumentStatusBadge status={doc.status} />
      </div>
      <p className="mt-1 text-sm text-slate-400">
        {doc.media_type} · {doc.original_filename}
      </p>

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
          <div className="space-y-4">
            {doc.processing_error && (
              <div className="rounded border border-amber-900 bg-amber-950/30 p-3 text-sm text-amber-300">
                {doc.processing_error}
              </div>
            )}
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <dt className="text-slate-500">Status</dt>
              <dd className="text-slate-200">{doc.status}</dd>
              <dt className="text-slate-500">SHA-256</dt>
              <dd className="break-all text-slate-200">{doc.sha256 ?? "—"}</dd>
              <dt className="text-slate-500">Extractor</dt>
              <dd className="text-slate-200">{doc.doc_metadata.extractor ?? "—"}</dd>
              <dt className="text-slate-500">Pages</dt>
              <dd className="text-slate-200">{doc.doc_metadata.page_count ?? "—"}</dd>
              <dt className="text-slate-500">Chunks indexed</dt>
              <dd className="text-slate-200">{doc.doc_metadata.chunk_count ?? "—"}</dd>
              <dt className="text-slate-500">Structure detected</dt>
              <dd className="text-slate-200">{doc.doc_metadata.used_structure_detection ? "Yes" : "No (plain-text fallback)"}</dd>
            </dl>
            {doc.doc_metadata.warnings && doc.doc_metadata.warnings.length > 0 && (
              <ul className="list-inside list-disc text-xs text-slate-500">
                {doc.doc_metadata.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
            <div className="flex gap-2 pt-2">
              {(doc.status === "failed" || doc.status === "ocr_required") && (
                <button
                  onClick={handleRetry}
                  disabled={retrying}
                  className="rounded border border-slate-700 px-3 py-1.5 text-xs hover:bg-slate-800 disabled:opacity-50"
                >
                  {retrying ? "Retrying…" : "Retry Processing"}
                </button>
              )}
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="rounded border border-red-900 px-3 py-1.5 text-xs text-red-300 hover:bg-red-950/40 disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        )}

        {tab === "Content" && (
          <div>
            {doc.status !== "ready" && (
              <p className="text-sm text-slate-500">
                Extracted text is only available once the document is READY (current status: {doc.status}).
              </p>
            )}
            {doc.status === "ready" && contentQuery.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
            {doc.status === "ready" && contentQuery.data && (
              <pre className="whitespace-pre-wrap rounded border border-slate-800 bg-slate-950/50 p-4 text-sm text-slate-300">
                {contentQuery.data}
              </pre>
            )}
          </div>
        )}

        {tab === "Analysis" && (
          <div className="space-y-6">
            {doc.status !== "ready" ? (
              <p className="text-sm text-slate-500">Document must be READY to analyze.</p>
            ) : (
              <button
                onClick={handleAnalyze}
                disabled={analyzing}
                className="rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
              >
                {analyzing ? "Analyzing…" : "Run Analysis"}
              </button>
            )}
            {analyzeError && <p className="text-sm text-amber-400">{analyzeError}</p>}
            {analysis && (
              <div className="space-y-4">
                {analysis.document_type_extracted && (
                  <p className="text-sm text-slate-300">
                    <span className="text-slate-500">Document type (EXTRACTED):</span> {analysis.document_type_extracted}
                  </p>
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
          <div>
            {doc.status !== "ready" ? (
              <p className="text-sm text-slate-500">Document must be READY to ask questions.</p>
            ) : (
              <div className="flex gap-2">
                <input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about this document"
                  className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
                />
                <button
                  onClick={handleAsk}
                  disabled={asking || !question.trim()}
                  className="rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
                >
                  {asking ? "Asking…" : "Submit Question"}
                </button>
              </div>
            )}
            {askError && <p className="mt-2 text-sm text-amber-400">{askError}</p>}

            <div className="mt-6 space-y-4">
              {askHistory.map((h, i) => (
                <div key={i} className="rounded border border-slate-800 p-3 text-sm">
                  <div className="text-slate-500">Q: {h.question}</div>
                  {h.answer ? (
                    <>
                      <div className="mt-1 flex items-center gap-2">
                        <span className="text-slate-200">{h.answer}</span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                            h.answerMethod === "extractive"
                              ? "bg-emerald-950 text-emerald-400"
                              : "bg-slate-800 text-slate-400"
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
                        <ul className="mt-2 space-y-1">
                          {h.citations.map((c, j) => (
                            <li key={j} className="rounded bg-slate-950/60 p-2 text-xs text-slate-400">
                              <div className="font-medium text-slate-300">{c.label}</div>
                              <div className="mt-1">{c.excerpt}</div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  ) : (
                    <div className="mt-1 text-amber-400">Insufficient document evidence to answer.</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "Citations" && (
          <div>
            {allCitations.length === 0 && (
              <p className="text-sm text-slate-500">
                No citations yet — citations appear here as you ask questions in the Ask tab.
              </p>
            )}
            <ul className="space-y-2">
              {allCitations.map((c, i) => (
                <li key={i} className="rounded border border-slate-800 p-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-emerald-950 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                      DOCUMENT EVIDENCE
                    </span>
                    <span className="font-medium text-slate-200">{c.label}</span>
                  </div>
                  <div className="mt-1 text-slate-400">{c.excerpt}</div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function FactSection({ title, facts }: { title: string; facts: { value: string; provenance: string }[] }) {
  if (facts.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-slate-300">{title}</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {facts.map((f, i) => (
          <li key={i} className="flex justify-between rounded border border-slate-800 px-2 py-1">
            <span className="text-slate-200">{f.value}</span>
            <span className="text-xs text-slate-500">{f.provenance}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TextListSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-sm font-medium text-slate-300">{title}</h3>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-300">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
