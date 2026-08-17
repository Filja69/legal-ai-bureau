import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { ResearchView } from "@/features/research/ResearchView";

export default function ResearchPage() {
  return (
    <AppShell>
      {/* useSearchParams() (for the Assistant's honest ?q= routing —
          see docs/UX-ASSISTANT-ROUTING.md) requires a Suspense boundary,
          otherwise Next.js opts the whole page out of static rendering. */}
      <Suspense fallback={null}>
        <ResearchView />
      </Suspense>
    </AppShell>
  );
}
