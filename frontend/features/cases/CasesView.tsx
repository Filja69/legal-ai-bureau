"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createCase, listCases } from "@/api/legal";
import { useAuth } from "@/hooks/useAuth";

export function CasesView() {
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [clientName, setClientName] = useState("");
  const [counterpartyName, setCounterpartyName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const casesQuery = useQuery({
    queryKey: ["cases", workspaceId],
    queryFn: () => listCases(workspaceId!),
    enabled: !!workspaceId,
  });

  async function handleCreate() {
    if (!title.trim() || !workspaceId) return;
    setCreating(true);
    setError(null);
    try {
      await createCase(workspaceId, {
        title,
        clientName: clientName || undefined,
        counterpartyName: counterpartyName || undefined,
      });
      setTitle("");
      setClientName("");
      setCounterpartyName("");
      await queryClient.invalidateQueries({ queryKey: ["cases", workspaceId] });
    } catch {
      setError("Не удалось создать дело.");
    } finally {
      setCreating(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-slate-500">Выберите рабочее пространство, чтобы увидеть дела.</div>;
  }

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-8">
      <h1 className="text-2xl font-semibold">Дела</h1>

      <div className="mt-6 space-y-3 rounded border border-slate-800 p-4">
        <h2 className="text-sm font-medium text-slate-300">Новое дело</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Название"
          className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        />
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            placeholder="Клиент (необязательно)"
            className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          />
          <input
            value={counterpartyName}
            onChange={(e) => setCounterpartyName(e.target.value)}
            placeholder="Контрагент (необязательно)"
            className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          />
        </div>
        <button
          onClick={handleCreate}
          disabled={creating || !title.trim()}
          className="w-full rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50 sm:w-auto"
        >
          {creating ? "Создание…" : "Создать дело"}
        </button>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      <section className="mt-8">
        <h2 className="text-lg font-medium">Все дела</h2>
        {casesQuery.isLoading && <p className="mt-2 text-sm text-slate-500">Загрузка…</p>}
        {casesQuery.isError && <p className="mt-2 text-sm text-red-400">Не удалось загрузить дела.</p>}
        {casesQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">Пока нет дел.</p>}
        <ul className="mt-2 space-y-2">
          {casesQuery.data?.map((c) => (
            <li key={c.id} className="rounded border border-slate-800 p-3 text-sm">
              <Link href={`/cases/${c.id}`} className="font-medium text-slate-200 hover:underline">
                {c.title}
              </Link>
              <div className="text-slate-500">
                {c.status}
                {c.client_name && ` · Клиент: ${c.client_name}`}
                {c.counterparty_name && ` · против: ${c.counterparty_name}`}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
