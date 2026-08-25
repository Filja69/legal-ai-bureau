import type { ReactNode } from "react";
import clsx from "clsx";

// Base panel used across every redesigned surface (Case Detail, Documents,
// Contracts, Research, Knowledge) — see legal_ai_redesign_pack §.card.
export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("rounded-panel border border-line bg-panel p-[18px] shadow-sm", className)}>{children}</div>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-3.5 flex items-start justify-between gap-3">
      <div>
        <h3 className="m-0 text-[15px] font-semibold text-ink">{title}</h3>
        {description && <p className="mt-1 text-[13px] text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
