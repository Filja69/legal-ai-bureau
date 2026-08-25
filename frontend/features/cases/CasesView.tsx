"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createCase, listCases } from "@/api/legal";
import { useAuth } from "@/hooks/useAuth";
import { Badge, Button, Card, CardHeader, PageHeader, toneForSeverity } from "@/components/ui";

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
    return <div className="p-8 text-sm text-muted">Выберите рабочее пространство, чтобы увидеть дела.</div>;
  }

  return (
    <div className="mx-auto max-w-5xl p-4 sm:p-8">
      <PageHeader title="Дела" description="Все дела рабочего пространства и создание нового." />

      <Card className="mb-8">
        <CardHeader title="Новое дело" />
        <div className="space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Название"
            className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink placeholder:text-slate-400"
          />
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder="Клиент (необязательно)"
              className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink placeholder:text-slate-400"
            />
            <input
              value={counterpartyName}
              onChange={(e) => setCounterpartyName(e.target.value)}
              placeholder="Контрагент (необязательно)"
              className="w-full rounded-lg border border-line bg-white p-2.5 text-sm text-ink placeholder:text-slate-400"
            />
          </div>
          <Button variant="primary" onClick={handleCreate} disabled={creating || !title.trim()}>
            {creating ? "Создание…" : "Создать дело"}
          </Button>
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-semibold text-ink">Все дела</h2>
        {casesQuery.isLoading && <p className="text-sm text-muted">Загрузка…</p>}
        {casesQuery.isError && <p className="text-sm text-danger">Не удалось загрузить дела.</p>}
        {casesQuery.data?.length === 0 && <p className="text-sm text-muted">Пока нет дел.</p>}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {casesQuery.data?.map((c) => (
            <Link key={c.id} href={`/cases/${c.id}`}>
              <Card className="h-full transition-shadow hover:shadow-panel">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-semibold text-ink">{c.title}</span>
                  <Badge tone={toneForSeverity(c.status)}>{c.status}</Badge>
                </div>
                <div className="mt-2 space-y-0.5 text-xs text-muted">
                  {c.client_name && <div>Клиент: {c.client_name}</div>}
                  {c.counterparty_name && <div>Против: {c.counterparty_name}</div>}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
