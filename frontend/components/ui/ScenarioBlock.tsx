import type { ReactNode } from "react";

export function ScenarioBlock({
  label,
  scenario,
  why,
  supporting,
  against,
}: {
  label: ReactNode;
  scenario: ReactNode;
  why: ReactNode;
  supporting: string[];
  against: string[];
}) {
  return (
    <div className="rounded-xl border border-line bg-white p-3.5">
      <span className="inline-flex items-center rounded-full bg-violet-soft px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-violet">
        {label}
      </span>
      <p className="mt-2 text-sm font-semibold leading-snug text-ink">{scenario}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{why}</p>
      <div className="mt-2.5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-success">За</div>
          <ul className="mt-1 space-y-1 text-xs text-slate-600">
            {supporting.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wide text-danger">Против</div>
          <ul className="mt-1 space-y-1 text-xs text-slate-600">
            {against.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
