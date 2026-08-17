"use client";

import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { getIndexStatus } from "@/api/knowledge";
import { KnowledgeNav } from "./KnowledgeNav";

export function KnowledgeOverviewView() {
  const statusQuery = useQuery({ queryKey: ["knowledge", "index-status"], queryFn: getIndexStatus, retry: false });

  const isForbidden = axios.isAxiosError(statusQuery.error) && statusQuery.error.response?.status === 403;

  return (
    <div className="mx-auto max-w-4xl p-4 sm:p-8">
      <h1 className="text-2xl font-semibold">База знаний</h1>
      <div className="mt-4">
        <KnowledgeNav />
      </div>

      <div className="mt-6">
        {statusQuery.isLoading && <p className="text-sm text-slate-500">Загрузка…</p>}
        {isForbidden && (
          <p className="text-sm text-red-400">Для просмотра статуса базы знаний требуется роль Admin или Owner.</p>
        )}
        {statusQuery.isError && !isForbidden && <p className="text-sm text-red-400">Не удалось загрузить статус индекса.</p>}

        {statusQuery.data && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded border border-slate-800 p-3">
                <div className="text-xs text-slate-500">Всего фрагментов</div>
                <div className="text-xl font-semibold">{statusQuery.data.total_chunks}</div>
              </div>
              <div className="rounded border border-slate-800 p-3">
                <div className="text-xs text-slate-500">Mock-фрагментов</div>
                <div className="text-xl font-semibold">{statusQuery.data.mock_chunks}</div>
              </div>
              <div className="rounded border border-slate-800 p-3">
                <div className="text-xs text-slate-500">Ошибок embedding</div>
                <div className="text-xl font-semibold">{statusQuery.data.failed_embeddings}</div>
              </div>
              <div className="rounded border border-slate-800 p-3">
                <div className="text-xs text-slate-500">В очереди на embedding</div>
                <div className="text-xl font-semibold">{statusQuery.data.pending_embeddings}</div>
              </div>
            </div>

            <div className="rounded border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-300">Активный Embedding</h2>
              <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                <dt className="text-slate-500">Provider</dt>
                <dd className="text-slate-200">{statusQuery.data.active_embedding.provider}</dd>
                <dt className="text-slate-500">Model</dt>
                <dd className="text-slate-200">{statusQuery.data.active_embedding.model}</dd>
                <dt className="text-slate-500">Namespace</dt>
                <dd className="text-slate-200">{statusQuery.data.active_embedding.namespace}</dd>
                <dt className="text-slate-500">Chunks in active namespace</dt>
                <dd className="text-slate-200">{statusQuery.data.active_embedding.chunks_in_active_namespace}</dd>
              </dl>
            </div>

            <div className="rounded border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-300">By Document Type</h2>
              <ul className="mt-2 space-y-1 text-sm">
                {Object.entries(statusQuery.data.by_document_type).map(([type, count]) => (
                  <li key={type} className="flex justify-between text-slate-400">
                    <span>{type}</span>
                    <span className="text-slate-200">{count}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-300">By Namespace</h2>
              <ul className="mt-2 space-y-1 text-sm">
                {Object.entries(statusQuery.data.by_namespace).map(([ns, count]) => (
                  <li key={ns} className="flex justify-between text-slate-400">
                    <span>{ns}</span>
                    <span className="text-slate-200">{count}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
