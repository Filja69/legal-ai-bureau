import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { SearchView } from "@/features/search/SearchView";

export default function SearchPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-8 text-sm text-slate-500">Loading…</div>}>
        <SearchView />
      </Suspense>
    </AppShell>
  );
}
