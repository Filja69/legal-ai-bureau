import type { ReactNode } from "react";
import clsx from "clsx";

const TONE_STYLE = {
  info: "bg-brand-soft border-blue-200 text-blue-900",
  warning: "bg-warning-soft border-amber-200 text-amber-900",
  danger: "bg-danger-soft border-red-200 text-red-900",
} as const;

export function Notice({ tone = "info", children }: { tone?: keyof typeof TONE_STYLE; children: ReactNode }) {
  return <div className={clsx("rounded-xl border p-3.5 text-[13px] leading-relaxed", TONE_STYLE[tone])}>{children}</div>;
}
