import type { ReactNode } from "react";
import clsx from "clsx";

const ACCENT = {
  blue: "border-l-brand",
  green: "border-l-emerald-500",
  amber: "border-l-amber-500",
  red: "border-l-red-500",
  violet: "border-l-violet-500",
} as const;

// Executive-summary tile: one label + one short qualitative insight, with a
// colored left accent instead of a full-tone badge — reads as "here is the
// answer" rather than another findings card.
export function InsightTile({
  label,
  accent = "blue",
  children,
}: {
  label: ReactNode;
  accent?: keyof typeof ACCENT;
  children: ReactNode;
}) {
  return (
    <div className={clsx("rounded-xl border border-line border-l-4 bg-white p-3.5", ACCENT[accent])}>
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1.5 text-sm leading-relaxed text-ink">{children}</div>
    </div>
  );
}
