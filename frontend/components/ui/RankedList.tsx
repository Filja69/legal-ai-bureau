import type { ReactNode } from "react";

export function RankedList({ children }: { children: ReactNode }) {
  return <ol className="space-y-2">{children}</ol>;
}

export function RankedItem({ rank, title, children, badge }: { rank: number; title: ReactNode; children?: ReactNode; badge?: ReactNode }) {
  return (
    <li className="flex gap-3 rounded-xl border border-line bg-white p-3.5">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-panel-muted text-xs font-bold text-slate-600">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-ink">{title}</span>
          {badge}
        </div>
        {children && <div className="mt-1 text-[13px] leading-relaxed text-slate-600">{children}</div>}
      </div>
    </li>
  );
}
