"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ru } from "@/lib/copy";

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { user, workspaceId, selectWorkspace } = useAuth();
  const router = useRouter();
  const [query, setQuery] = useState("");

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    router.push(`/search?q=${encodeURIComponent(query.trim())}`);
  }

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-800 px-3 sm:gap-4 sm:px-4">
      <button
        onClick={onMenuClick}
        aria-label={ru.nav.openMenu}
        className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 md:hidden"
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M2.5 5h15M2.5 10h15M2.5 15h15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>

      <form onSubmit={handleSearch} className="min-w-0 flex-1 sm:max-w-xl">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по делам, договорам, документам, исследованиям, праву..."
          className="w-full rounded border border-slate-800 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:border-slate-600 focus:outline-none"
        />
      </form>

      <div className="hidden flex-1 sm:block" />

      {user && user.memberships.length > 1 && (
        <select
          value={workspaceId ?? ""}
          onChange={(e) => selectWorkspace(e.target.value)}
          className="hidden rounded border border-slate-800 bg-slate-900 px-2 py-1.5 text-sm text-slate-200 sm:block"
        >
          {user.memberships.map((m) => (
            <option key={m.workspace_id} value={m.workspace_id}>
              {m.workspace_name}
            </option>
          ))}
        </select>
      )}

      {user && user.memberships.length === 1 && (
        <span className="hidden truncate text-sm text-slate-400 sm:inline">{user.memberships[0].workspace_name}</span>
      )}

      {user?.is_dev_bypass && (
        <span className="hidden rounded border border-amber-900 bg-amber-950 px-2 py-0.5 text-[10px] font-semibold text-amber-300 sm:inline-block">
          DEV IDENTITY
        </span>
      )}

      {process.env.NEXT_PUBLIC_FEEDBACK_URL && (
        <a
          href={process.env.NEXT_PUBLIC_FEEDBACK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hidden text-sm text-slate-400 hover:text-slate-200 hover:underline sm:inline"
        >
          {ru.common.reportIssue}
        </a>
      )}

      <span className="hidden truncate text-sm text-slate-300 sm:inline">{user?.name ?? user?.email ?? "…"}</span>
    </header>
  );
}
