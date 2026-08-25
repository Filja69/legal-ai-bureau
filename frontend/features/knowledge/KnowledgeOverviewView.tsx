"use client";

import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { getIndexStatus } from "@/api/knowledge";
import { Card, CardHeader, Notice, PageHeader } from "@/components/ui";
import { KnowledgeNav } from "./KnowledgeNav";

export function KnowledgeOverviewView() {
  const statusQuery = useQuery({ queryKey: ["knowledge", "index-status"], queryFn: getIndexStatus, retry: false });

  const isForbidden = axios.isAxiosError(statusQuery.error) && statusQuery.error.response?.status === 403;

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader title="База знаний" />
      <div className="mb-6">
        <KnowledgeNav />
      </div>

      {statusQuery.isLoading && <p className="text-sm text-muted">Загрузка…</p>}
      {isForbidden && <Notice tone="danger">Для просмотра статуса базы знаний требуется роль Admin или Owner.</Notice>}
      {statusQuery.isError && !isForbidden && <Notice tone="danger">Не удалось загрузить статус индекса.</Notice>}

      {statusQuery.data && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card>
              <div className="text-xs text-muted">Всего фрагментов</div>
              <div className="mt-1 text-xl font-semibold text-ink">{statusQuery.data.total_chunks}</div>
            </Card>
            <Card>
              <div className="text-xs text-muted">Mock-фрагментов</div>
              <div className="mt-1 text-xl font-semibold text-ink">{statusQuery.data.mock_chunks}</div>
            </Card>
            <Card>
              <div className="text-xs text-muted">Ошибок embedding</div>
              <div className="mt-1 text-xl font-semibold text-ink">{statusQuery.data.failed_embeddings}</div>
            </Card>
            <Card>
              <div className="text-xs text-muted">В очереди на embedding</div>
              <div className="mt-1 text-xl font-semibold text-ink">{statusQuery.data.pending_embeddings}</div>
            </Card>
          </div>

          <Card>
            <CardHeader title="Активный Embedding" />
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-muted">Provider</dt>
              <dd className="text-ink">{statusQuery.data.active_embedding.provider}</dd>
              <dt className="text-muted">Model</dt>
              <dd className="text-ink">{statusQuery.data.active_embedding.model}</dd>
              <dt className="text-muted">Namespace</dt>
              <dd className="text-ink">{statusQuery.data.active_embedding.namespace}</dd>
              <dt className="text-muted">Chunks in active namespace</dt>
              <dd className="text-ink">{statusQuery.data.active_embedding.chunks_in_active_namespace}</dd>
            </dl>
          </Card>

          <Card>
            <CardHeader title="By Document Type" />
            <ul className="space-y-1.5 text-sm">
              {Object.entries(statusQuery.data.by_document_type).map(([type, count]) => (
                <li key={type} className="flex justify-between text-slate-600">
                  <span>{type}</span>
                  <span className="text-ink">{count}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="By Namespace" />
            <ul className="space-y-1.5 text-sm">
              {Object.entries(statusQuery.data.by_namespace).map(([ns, count]) => (
                <li key={ns} className="flex justify-between text-slate-600">
                  <span>{ns}</span>
                  <span className="text-ink">{count}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
