"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listDocuments, uploadDocument } from "@/api/documents";
import { useAuth } from "@/hooks/useAuth";
import { Button, Card, Notice, PageHeader } from "@/components/ui";
import { DocumentStatusBadge } from "./DocumentStatusBadge";

const TYPE_LABEL: Record<string, string> = {
  contract: "Договор",
  evidence: "Доказательство",
  correspondence: "Переписка",
  generated: "Сгенерирован",
  other: "Другое",
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
      setError(detail ?? "Загрузка не удалась — backend доступен?");
    } finally {
      setUploading(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-muted">Выберите рабочее пространство, чтобы увидеть документы.</div>;
  }

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader
        title="Документы"
        description={
          <>
            PDF (с текстовым слоем), DOCX, TXT и XLSX автоматически распознаются, разбиваются на фрагменты и
            индексируются при загрузке. Сканы PDF без текстового слоя честно помечаются{" "}
            <span className="font-semibold text-warning">ТРЕБУЕТСЯ OCR</span> — OCR пока не реализован.
          </>
        }
      />

      <Card className="mb-8">
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt,.xlsx,.csv,.png,.jpg,.jpeg"
            className="w-full text-sm text-ink sm:w-auto"
          />
          <Button variant="primary" onClick={handleUpload} disabled={uploading}>
            {uploading ? "Загрузка…" : "Загрузить"}
          </Button>
        </div>
        {error && (
          <div className="mt-3">
            <Notice tone="danger">{error}</Notice>
          </div>
        )}
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-ink">Загруженные документы</h2>
        {documentsQuery.isLoading && <p className="text-sm text-muted">Загрузка…</p>}
        {documentsQuery.isError && <p className="text-sm text-danger">Не удалось загрузить список документов.</p>}
        {documentsQuery.data?.length === 0 && <p className="text-sm text-muted">Пока нет документов.</p>}
        <div className="space-y-2.5">
          {documentsQuery.data?.map((doc) => (
            <Card key={doc.id} className="flex flex-wrap items-center justify-between gap-2 p-3.5">
              <div className="min-w-0">
                <Link href={`/documents/${doc.id}`} className="font-medium text-ink hover:underline">
                  {doc.title}
                </Link>
                <div className="text-xs text-muted">
                  {TYPE_LABEL[doc.document_type] ?? doc.document_type} · {formatSize(doc.size_bytes)}
                  {doc.created_at && ` · ${new Date(doc.created_at).toLocaleDateString()}`}
                </div>
              </div>
              <DocumentStatusBadge status={doc.status} />
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
