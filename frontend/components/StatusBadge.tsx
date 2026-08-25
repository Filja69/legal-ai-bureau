// Reusable citation/verification status badge — used across Research, Contract
// risks, and Knowledge admin. Never relabels MOCK as VERIFIED or hides
// UNVERIFIED (Phase 8 brief §12/§37) — the color communicates severity, the
// TEXT is always the real backend status word.

const STYLES: Record<string, string> = {
  verified: "bg-success-soft text-success border border-emerald-200",
  mock: "bg-warning-soft text-warning border border-amber-200",
  unverified: "bg-slate-100 text-slate-600 border border-slate-200",
  broken: "bg-danger-soft text-danger border border-red-200",
  temporally_invalid: "bg-danger-soft text-danger border border-red-200",
  unsupported_critical: "bg-danger-soft text-danger border border-red-200",
  blocked: "bg-slate-100 text-slate-500 border border-dashed border-slate-300",
};

const LABELS: Record<string, string> = {
  verified: "VERIFIED",
  mock: "MOCK",
  unverified: "UNVERIFIED",
  broken: "BROKEN",
  temporally_invalid: "TEMPORALLY INVALID",
  unsupported_critical: "UNSUPPORTED",
  blocked: "BLOCKED",
};

export function StatusBadge({ status, className = "" }: { status: string; className?: string }) {
  const key = status.toLowerCase();
  const style = STYLES[key] ?? "bg-slate-100 text-slate-600 border border-slate-200";
  const label = LABELS[key] ?? status.toUpperCase();
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wide ${style} ${className}`}>
      {label}
    </span>
  );
}
