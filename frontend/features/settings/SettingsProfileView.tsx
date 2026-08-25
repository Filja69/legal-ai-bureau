"use client";

import { useAuth } from "@/hooks/useAuth";
import { Card, PageHeader } from "@/components/ui";
import { SettingsNav } from "./SettingsNav";

export function SettingsProfileView() {
  const { user, isLoadingUser, logout } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <PageHeader title="Настройки" />
      <div className="mb-6">
        <SettingsNav />
      </div>

      <Card>
        {isLoadingUser && <p className="text-sm text-muted">Загрузка…</p>}
        {user && (
          <dl className="grid grid-cols-[140px_1fr] gap-y-3 text-sm">
            <dt className="text-muted">Имя</dt>
            <dd className="text-ink">{user.name ?? "—"}</dd>
            <dt className="text-muted">Email</dt>
            <dd className="text-ink">{user.email ?? "—"}</dd>
            <dt className="text-muted">Режим входа</dt>
            <dd className="text-ink">{user.is_dev_bypass ? "Dev-режим (вход не требуется)" : "Аутентифицирован"}</dd>
          </dl>
        )}
        <button
          onClick={logout}
          className="mt-6 rounded-lg border border-line px-3.5 py-2 text-sm font-semibold text-ink hover:bg-panel-muted"
        >
          Выйти
        </button>
      </Card>
    </div>
  );
}
