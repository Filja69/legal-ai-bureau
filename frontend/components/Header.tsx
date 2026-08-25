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
    <header className="flex h-[72px] shrink-0 items-center gap-2 border-b border-line bg-white/95 px-3 backdrop-blur sm:gap-4 sm:px-6">
      <button
        onClick={onMenuClick}
        aria-label={ru.nav.openMenu}
        className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-ink md:hidden"
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
          className="w-full rounded-lg border border-line bg-white px-3.5 py-2.5 text-sm text-ink placeholder:text-slate-400 focus:border-blue-300 focus:outline-none focus:ring-4 focus:ring-blue-600/10"
        />
      </form>

      <div className="hidden flex-1 sm:block" />

      {user && user.memberships.length > 1 && (
        <select
          value={workspaceId ?? ""}
          onChange={(e) => selectWorkspace(e.target.value)}
          className="hidden rounded-lg border border-line bg-white px-2 py-2 text-sm text-ink sm:block"
        >
          {user.memberships.map((m) => (
            <option key={m.workspace_id} value={m.workspace_id}>
              {m.workspace_name}
            </option>
          ))}
        </select>
      )}

      {user && user.memberships.length === 1 && (
        <span className="hidden truncate text-sm text-muted sm:inline">{user.memberships[0].workspace_name}</span>
      )}

      {user?.is_dev_bypass && (
        <span className="hidden rounded-full border border-amber-200 bg-warning-soft px-2.5 py-1 text-[10px] font-bold text-warning sm:inline-block">
          DEV IDENTITY
        </span>
      )}

      {process.env.NEXT_PUBLIC_FEEDBACK_URL && (
        <a
          href={process.env.NEXT_PUBLIC_FEEDBACK_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="hidden text-sm text-muted hover:text-ink hover:underline sm:inline"
        >
          {ru.common.reportIssue}
        </a>
      )}

      <span className="hidden truncate text-sm font-medium text-ink sm:inline">{user?.name ?? user?.email ?? "…"}</span>
    </header>
  );
}
