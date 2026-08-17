"use client";

import { useAuth } from "@/hooks/useAuth";
import { SettingsNav } from "./SettingsNav";

export function SettingsProfileView() {
  const { user, isLoadingUser, logout } = useAuth();

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-8">
      <h1 className="text-2xl font-semibold">Настройки</h1>
      <div className="mt-4">
        <SettingsNav />
      </div>

      <div className="mt-6">
        {isLoadingUser && <p className="text-sm text-slate-500">Загрузка…</p>}
        {user && (
          <dl className="grid grid-cols-[140px_1fr] gap-y-3 text-sm">
            <dt className="text-slate-500">Имя</dt>
            <dd className="text-slate-200">{user.name ?? "—"}</dd>
            <dt className="text-slate-500">Email</dt>
            <dd className="text-slate-200">{user.email ?? "—"}</dd>
            <dt className="text-slate-500">Режим входа</dt>
            <dd className="text-slate-200">{user.is_dev_bypass ? "Dev-режим (вход не требуется)" : "Аутентифицирован"}</dd>
          </dl>
        )}
        <button
          onClick={logout}
          className="mt-6 rounded border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
        >
          Выйти
        </button>
      </div>
    </div>
  );
}
