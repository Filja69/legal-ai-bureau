import type { ReactNode } from "react";

export function Checklist({ children }: { children: ReactNode }) {
  return <ul className="space-y-1.5">{children}</ul>;
}

export function ChecklistItem({ children, badge }: { children: ReactNode; badge?: ReactNode }) {
  return (
    <li className="flex items-start gap-2.5 rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-slate-700">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="mt-0.5 shrink-0 text-slate-300" aria-hidden="true">
        <rect x="2" y="2" width="12" height="12" rx="3" stroke="currentColor" strokeWidth="1.4" />
      </svg>
      <span className="min-w-0 flex-1">{children}</span>
      {badge}
    </li>
  );
}
