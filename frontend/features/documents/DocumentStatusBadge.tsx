import type { DocumentStatus } from "@/types/document";

// Process-state badge — deliberately separate from the shared StatusBadge
// component (components/StatusBadge.tsx), which is reserved for citation
// VERIFIED/MOCK/UNVERIFIED semantics. Document processing status is a
// different kind of fact and must not borrow that vocabulary.
const STYLES: Record<DocumentStatus, string> = {
  uploaded: "bg-slate-800 text-slate-300 border border-slate-700",
  processing: "bg-indigo-950 text-indigo-300 border border-indigo-900",
  ready: "bg-emerald-950 text-emerald-300 border border-emerald-900",
  failed: "bg-red-950 text-red-300 border border-red-900",
  ocr_required: "bg-amber-950 text-amber-300 border border-amber-900",
  unsupported: "bg-slate-800 text-slate-400 border border-slate-700 border-dashed",
};

const LABELS: Record<DocumentStatus, string> = {
  uploaded: "UPLOADED",
  processing: "PROCESSING",
  ready: "READY",
  failed: "FAILED",
  ocr_required: "OCR REQUIRED",
  unsupported: "UNSUPPORTED",
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
