import type { DocumentStatus } from "@/types/document";

// Process-state badge — deliberately separate from the shared StatusBadge
// component (components/StatusBadge.tsx), which is reserved for citation
// VERIFIED/MOCK/UNVERIFIED semantics. Document processing status is a
// different kind of fact and must not borrow that vocabulary.
const STYLES: Record<DocumentStatus, string> = {
  uploaded: "bg-slate-100 text-slate-600 border border-slate-200",
  processing: "bg-brand-soft text-brand-strong border border-blue-200",
  ready: "bg-success-soft text-success border border-emerald-200",
  failed: "bg-danger-soft text-danger border border-red-200",
  ocr_required: "bg-warning-soft text-warning border border-amber-200",
  unsupported: "bg-slate-100 text-slate-400 border border-dashed border-slate-300",
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
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wide ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
