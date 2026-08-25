import type { ReactNode } from "react";

export function Timeline({ children }: { children: ReactNode }) {
  return <div className="flex flex-col">{children}</div>;
}

export function TimelineRow({ date, children, isLast = false }: { date: ReactNode; children: ReactNode; isLast?: boolean }) {
  return (
    <div className="grid min-h-[56px] grid-cols-[90px_16px_1fr] gap-2.5">
      <div className="pt-0.5 text-xs text-muted">{date}</div>
      <div className="relative">
        <span className="absolute left-[5px] top-1 h-2 w-2 rounded-full bg-brand" />
        {!isLast && <span className="absolute left-2 top-[18px] bottom-[-4px] w-px bg-line" />}
      </div>
      <div className="pb-4">{children}</div>
    </div>
  );
}
