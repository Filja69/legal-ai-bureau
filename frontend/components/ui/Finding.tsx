import type { ReactNode } from "react";

// A single finding row — title + severity badge + body + optional source/meta
// chips. Used by Master Report findings, but generic enough to reuse for any
// evidence/contradiction-style list.
export function Finding({ title, badge, children, meta }: { title: ReactNode; badge?: ReactNode; children?: ReactNode; meta?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-white p-3.5">
      <div className="flex items-center justify-between gap-3">
        <h4 className="m-0 text-sm font-semibold text-ink">{title}</h4>
        {badge}
      </div>
      {children && <div className="mt-2 text-[13px] leading-relaxed text-slate-600">{children}</div>}
      {meta && <div className="mt-2.5 flex flex-wrap gap-2">{meta}</div>}
    </div>
  );
}
