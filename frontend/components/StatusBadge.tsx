// Reusable citation/verification status badge — used across Research, Contract
// risks, and Knowledge admin. Never relabels MOCK as VERIFIED or hides
// UNVERIFIED (Phase 8 brief §12/§37) — the color communicates severity, the
// TEXT is always the real backend status word.

const STYLES: Record<string, string> = {
  verified: "bg-emerald-950 text-emerald-300 border border-emerald-900",
  mock: "bg-amber-950 text-amber-300 border border-amber-900",
  unverified: "bg-slate-800 text-slate-300 border border-slate-700",
  broken: "bg-red-950 text-red-300 border border-red-900",
  temporally_invalid: "bg-red-950 text-red-300 border border-red-900",
  unsupported_critical: "bg-red-950 text-red-300 border border-red-900",
  blocked: "bg-slate-800 text-slate-400 border border-slate-700 border-dashed",
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
  const style = STYLES[key] ?? "bg-slate-800 text-slate-300 border border-slate-700";
  const label = LABELS[key] ?? status.toUpperCase();
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${style} ${className}`}>
      {label}
    </span>
  );
}
