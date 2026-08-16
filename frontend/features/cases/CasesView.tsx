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
      setError("Could not create case.");
    } finally {
      setCreating(false);
    }
  }

  if (!workspaceId) {
    return <div className="p-8 text-sm text-slate-500">Select a workspace to view cases.</div>;
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Cases</h1>

      <div className="mt-6 space-y-3 rounded border border-slate-800 p-4">
        <h2 className="text-sm font-medium text-slate-300">New Case</h2>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Title"
          className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
        />
        <div className="flex gap-3">
          <input
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
            placeholder="Client (optional)"
            className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          />
          <input
            value={counterpartyName}
            onChange={(e) => setCounterpartyName(e.target.value)}
            placeholder="Counterparty (optional)"
            className="w-full rounded border border-slate-700 bg-slate-900 p-2 text-sm"
          />
        </div>
        <button
          onClick={handleCreate}
          disabled={creating || !title.trim()}
          className="rounded bg-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
        >
          {creating ? "Creating…" : "Create Case"}
        </button>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      <section className="mt-8">
        <h2 className="text-lg font-medium">All Cases</h2>
        {casesQuery.isLoading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
        {casesQuery.isError && <p className="mt-2 text-sm text-red-400">Could not load cases.</p>}
        {casesQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">No cases yet.</p>}
        <ul className="mt-2 space-y-2">
          {casesQuery.data?.map((c) => (
            <li key={c.id} className="rounded border border-slate-800 p-3 text-sm">
              <Link href={`/cases/${c.id}`} className="font-medium text-slate-200 hover:underline">
                {c.title}
              </Link>
              <div className="text-slate-500">
                {c.status}
                {c.client_name && ` · Client: ${c.client_name}`}
                {c.counterparty_name && ` · vs. ${c.counterparty_name}`}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
