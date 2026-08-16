"use client";

import { useAuth } from "@/hooks/useAuth";
import { SettingsNav } from "./SettingsNav";

export function SettingsWorkspaceView() {
  const { user, workspaceId, selectWorkspace, isLoadingUser } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <div className="mt-4">
        <SettingsNav />
      </div>

      <div className="mt-6">
        {isLoadingUser && <p className="text-sm text-slate-500">Loading…</p>}
        {user?.is_dev_bypass && (
          <p className="text-sm text-slate-500">
            Running under a dev-identity bypass — workspace membership isn&apos;t tracked in this mode.
          </p>
        )}
        {user && !user.is_dev_bypass && user.memberships.length === 0 && (
          <p className="text-sm text-slate-500">No workspace memberships.</p>
        )}
        {user && !user.is_dev_bypass && user.memberships.length > 0 && (
          <ul className="space-y-2">
            {user.memberships.map((m) => (
              <li
                key={m.workspace_id}
                className={`flex items-center justify-between rounded border p-3 text-sm ${
                  m.workspace_id === workspaceId ? "border-slate-500" : "border-slate-800"
                }`}
              >
                <div>
                  <div className="font-medium text-slate-200">{m.workspace_name}</div>
                  <div className="text-slate-500">Role: {m.role}</div>
                </div>
                {m.workspace_id === workspaceId ? (
                  <span className="text-xs text-emerald-400">Active</span>
                ) : (
                  <button
                    onClick={() => selectWorkspace(m.workspace_id)}
                    className="rounded border border-slate-700 px-2 py-1 text-xs hover:bg-slate-800"
                  >
                    Switch
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
