"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";

export function Header() {
  const { user, workspaceId, selectWorkspace } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    router.push(`/search?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-slate-800 px-4">
      <form onSubmit={handleSearch} className="flex-1 max-w-xl">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search cases, contracts, documents, research, law..."
          className="w-full rounded border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
        />
      </form>

      <div className="flex-1" />

      {user && user.memberships.length > 1 && (
        <select
          value={workspaceId ?? ""}
          onChange={(e) => selectWorkspace(e.target.value)}
          className="rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm text-slate-200"
        >
          {user.memberships.map((m) => (
            <option key={m.workspace_id} value={m.workspace_id}>
              {m.workspace_name}
            </option>
          ))}
        </select>
      )}

      {user && user.memberships.length === 1 && (
        <span className="text-sm text-slate-400">{user.memberships[0].workspace_name}</span>
      )}

      {user?.is_dev_bypass && (
        <span className="rounded bg-amber-950 px-2 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-900">
          DEV IDENTITY
        </span>
      )}

      {process.env.NEXT_PUBLIC_FEEDBACK_URL && (
        <a
          href={process.env.NEXT_PUBLIC_FEEDBACK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-slate-400 hover:text-slate-200 hover:underline"
        >
          Report an issue
        </a>
      )}

      <span className="text-sm text-slate-300">{user?.name ?? user?.email ?? "..."}</span>
    </header>
  );
}
