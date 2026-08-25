import type { ReactNode } from "react";

export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-auto rounded-xl border border-line">
      <table className="w-full border-collapse text-[13px]">{children}</table>
    </div>
  );
}

export function Th({ children }: { children: ReactNode }) {
  return <th className="border-b border-line bg-panel-muted px-3 py-2.5 text-left font-semibold text-slate-600">{children}</th>;
}

export function Td({ children, className }: { children: ReactNode; className?: string }) {
  return <td className={`border-b border-line px-3 py-2.5 align-top ${className ?? ""}`}>{children}</td>;
}
