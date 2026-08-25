"use client";

import { useAuth } from "@/hooks/useAuth";
import { Badge, Card, PageHeader } from "@/components/ui";
import { SettingsNav } from "./SettingsNav";

export function SettingsWorkspaceView() {
  const { user, workspaceId, selectWorkspace, isLoadingUser } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <PageHeader title="Settings" />
      <div className="mb-6">
        <SettingsNav />
      </div>

      {isLoadingUser && <p className="text-sm text-muted">Loading…</p>}
      {user?.is_dev_bypass && (
        <p className="text-sm text-muted">Running under a dev-identity bypass — workspace membership isn&apos;t tracked in this mode.</p>
      )}
      {user && !user.is_dev_bypass && user.memberships.length === 0 && <p className="text-sm text-muted">No workspace memberships.</p>}
      {user && !user.is_dev_bypass && user.memberships.length > 0 && (
        <div className="space-y-2">
          {user.memberships.map((m) => (
            <Card key={m.workspace_id} className={`flex items-center justify-between ${m.workspace_id === workspaceId ? "border-blue-300" : ""}`}>
              <div>
                <div className="font-medium text-ink">{m.workspace_name}</div>
                <div className="text-sm text-muted">Role: {m.role}</div>
              </div>
              {m.workspace_id === workspaceId ? (
                <Badge tone="green">Active</Badge>
              ) : (
                <button
                  onClick={() => selectWorkspace(m.workspace_id)}
                  className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink hover:bg-panel-muted"
                >
                  Switch
                </button>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
