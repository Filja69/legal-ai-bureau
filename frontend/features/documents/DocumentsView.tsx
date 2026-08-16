"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listDocuments, uploadDocument } from "@/api/documents";
import { useAuth } from "@/hooks/useAuth";
import { DocumentStatusBadge } from "./DocumentStatusBadge";

const TYPE_LABEL: Record<string, string> = {
  contract: "Contract",
  evidence: "Evidence",
  correspondence: "Correspondence",
  generated: "Generated",
  other: "Other",
};

function formatSize(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentsView() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const documentsQuery = useQuery({
    queryKey: ["documents", workspaceId],
    queryFn: () => listDocuments(workspaceId!),
    enabled: !!workspaceId,
  });

  async function handleUpload() {
    const file = fileInput.current?.files?.[0];
    if (!file || !workspaceId) return;
    setUploading(true);
    setError(null);
    try {
      await uploadDocument(workspaceId, file);
      if (fileInput.current) fileInput.current.value = "";
      await queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(detail ?? "Upload failed — is the backend running?");
    } finally {
      setUploading(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-slate-500">Select a workspace to view documents.</div>;
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Documents</h1>
      <p className="mt-2 text-sm text-slate-400">
        PDF (text-layer), DOCX, TXT, and XLSX are extracted, chunked, and indexed automatically on
        upload. Scanned PDFs with no text layer are honestly marked{" "}
        <span className="font-medium text-amber-400">OCR REQUIRED</span> — OCR is not implemented yet.
      </p>

      <div className="mt-4 flex items-center gap-3">
        <input ref={fileInput} type="file" accept=".pdf,.docx,.txt,.xlsx,.csv,.png,.jpg,.jpeg" className="text-sm" />
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="rounded bg-slate-700 px-3 py-1.5 text-sm hover:bg-slate-600 disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

      <section className="mt-8">
        <h2 className="text-lg font-medium">Uploaded Documents</h2>
        {documentsQuery.isLoading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
        {documentsQuery.isError && <p className="mt-2 text-sm text-red-400">Could not load documents.</p>}
        {documentsQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">No documents yet.</p>}
        <ul className="mt-2 space-y-2">
          {documentsQuery.data?.map((doc) => (
            <li key={doc.id} className="flex items-center justify-between rounded border border-slate-800 p-3 text-sm">
              <div>
                <Link href={`/documents/${doc.id}`} className="font-medium text-slate-200 hover:underline">
                  {doc.title}
                </Link>
                <div className="text-slate-500">
                  {TYPE_LABEL[doc.document_type] ?? doc.document_type} · {formatSize(doc.size_bytes)}
                  {doc.created_at && ` · ${new Date(doc.created_at).toLocaleDateString()}`}
                </div>
              </div>
              <DocumentStatusBadge status={doc.status} />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
