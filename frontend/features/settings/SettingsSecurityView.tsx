"use client";

import { useAuth } from "@/hooks/useAuth";
import { SettingsNav } from "./SettingsNav";

export function SettingsSecurityView() {
  const { user } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <div className="mt-4">
        <SettingsNav />
      </div>

      <div className="mt-6 space-y-4 text-sm">
        <div className="rounded border border-slate-800 p-4">
          <h2 className="font-medium text-slate-200">Session</h2>
          <p className="mt-1 text-slate-400">
            Your session token is stored only for this browser tab and is cleared when the tab closes or you sign
            out.
          </p>
        </div>
        <div className="rounded border border-slate-800 p-4">
          <h2 className="font-medium text-slate-200">Authentication mode</h2>
          <p className="mt-1 text-slate-400">
            {user?.is_dev_bypass
              ? "This environment is running with the developer identity bypass — no password is required. Do not use this configuration in production."
              : "Authenticated via password login with a signed, time-limited token."}
          </p>
        </div>
      </div>
    </div>
  );
}
