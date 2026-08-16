"use client";

import { useAuth } from "@/hooks/useAuth";
import { SettingsNav } from "./SettingsNav";

export function SettingsProfileView() {
  const { user, isLoadingUser, logout } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <div className="mt-4">
        <SettingsNav />
      </div>

      <div className="mt-6">
        {isLoadingUser && <p className="text-sm text-slate-500">Loading…</p>}
        {user && (
          <dl className="grid grid-cols-[140px_1fr] gap-y-3 text-sm">
            <dt className="text-slate-500">Name</dt>
            <dd className="text-slate-200">{user.name ?? "—"}</dd>
            <dt className="text-slate-500">Email</dt>
            <dd className="text-slate-200">{user.email ?? "—"}</dd>
            <dt className="text-slate-500">Identity mode</dt>
            <dd className="text-slate-200">{user.is_dev_bypass ? "Dev bypass (no login required)" : "Authenticated"}</dd>
          </dl>
        )}
        <button
          onClick={logout}
          className="mt-6 rounded border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
