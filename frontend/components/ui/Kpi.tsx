import type { ReactNode } from "react";

export function KpiGrid({ children }: { children: ReactNode }) {
  return <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">{children}</div>;
}

export function Kpi({ label, value }: { label: ReactNode; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/10 p-3.5">
      <span className="block text-xs text-slate-300">{label}</span>
      <strong className="mt-1 block text-xl text-white">{value}</strong>
    </div>
  );
}
