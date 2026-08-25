import type { ReactNode } from "react";

// Claim-vs-evidence layout for contradiction findings — "Утверждение → VS →
// доказательство". `left` is the pleaded/claimed proposition, `right` is the
// documentary evidence in tension with it.
export function CompareCard({
  title,
  left,
  right,
  caveat,
  badge,
}: {
  title: ReactNode;
  left: ReactNode;
  right: ReactNode;
  caveat?: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line bg-white p-3.5">
      <div className="flex items-center justify-between gap-2">
        <h4 className="m-0 text-sm font-semibold text-ink">{title}</h4>
        {badge}
      </div>
      <div className="mt-2.5 grid grid-cols-1 items-stretch gap-2 sm:grid-cols-[1fr_auto_1fr]">
        <div className="rounded-lg bg-panel-muted p-2.5 text-[13px] leading-relaxed text-slate-700">{left}</div>
        <div className="flex items-center justify-center text-xs font-bold text-slate-400">VS</div>
        <div className="rounded-lg bg-danger-soft p-2.5 text-[13px] leading-relaxed text-slate-700">{right}</div>
      </div>
      {caveat && <div className="mt-2 text-xs text-muted">Оговорка: {caveat}</div>}
    </div>
  );
}
