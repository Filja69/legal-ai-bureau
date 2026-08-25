import type { ReactNode } from "react";

// Dark gradient hero used at the top of a detail page's "30-second position"
// summary — see legal_ai_redesign_pack's .hero-case.
export function HeroBanner({
  kicker,
  title,
  description,
  badge,
  children,
}: {
  kicker: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  badge?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="mb-5 rounded-panel bg-gradient-to-br from-slate-900 via-slate-900 to-blue-900 p-6 text-white shadow-panel">
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-blue-300">{kicker}</div>
          <h2 className="mb-2 mt-1.5 text-2xl font-semibold leading-snug">{title}</h2>
          {description && <p className="max-w-3xl leading-relaxed text-slate-300">{description}</p>}
        </div>
        {badge}
      </div>
      {children}
    </section>
  );
}
