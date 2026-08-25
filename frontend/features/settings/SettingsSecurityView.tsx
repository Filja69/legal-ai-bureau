"use client";

import { useAuth } from "@/hooks/useAuth";
import { Card, CardHeader, PageHeader } from "@/components/ui";
import { SettingsNav } from "./SettingsNav";

export function SettingsSecurityView() {
  const { user } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <PageHeader title="Settings" />
      <div className="mb-6">
        <SettingsNav />
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Session" />
          <p className="text-sm text-slate-600">
            Your session token is stored only for this browser tab and is cleared when the tab closes or you sign
            out.
          </p>
        </Card>
        <Card>
          <CardHeader title="Authentication mode" />
          <p className="text-sm text-slate-600">
            {user?.is_dev_bypass
              ? "This environment is running with the developer identity bypass — no password is required. Do not use this configuration in production."
              : "Authenticated via password login with a signed, time-limited token."}
          </p>
        </Card>
      </div>
    </div>
  );
}
