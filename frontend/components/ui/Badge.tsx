import type { ReactNode } from "react";
import clsx from "clsx";

export type BadgeTone = "blue" | "green" | "amber" | "red" | "violet" | "gray";

const TONE_STYLE: Record<BadgeTone, string> = {
  blue: "bg-brand-soft text-brand-strong",
  green: "bg-success-soft text-success",
  amber: "bg-warning-soft text-warning",
  red: "bg-danger-soft text-danger",
  violet: "bg-violet-soft text-violet",
  gray: "bg-slate-100 text-slate-600",
};

// Maps the domain's existing severity/strength/status vocabularies onto a
// visual tone — this is presentation only, the underlying text is always
// whatever the backend/tests expect (never relabeled).
export function toneForSeverity(value: string): BadgeTone {
  const v = value.toLowerCase();
  if (v === "critical" || v === "red" || v === "danger" || v === "contradicted" || v === "conflicted" || v === "high") return "red";
  if (v === "warning" || v === "amber" || v === "disputed" || v === "weak" || v === "medium") return "amber";
  if (v === "success" || v === "green" || v === "supported" || v === "strong" || v === "low" || v === "ready") return "green";
  if (v === "inferred" || v === "violet") return "violet";
  if (v === "blue" || v === "moderate") return "blue";
  return "gray";
}

export function Badge({ children, tone = "gray", className }: { children: ReactNode; tone?: BadgeTone; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide",
        TONE_STYLE[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
