"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { searchGlobal, type GlobalSearchResultType } from "@/api/search";
import { useAuth } from "@/hooks/useAuth";

const TYPE_LABEL: Record<GlobalSearchResultType, { label: string; className: string; href: (id: string) => string }> = {
  CASE: { label: "Case", className: "bg-slate-800 text-slate-300", href: (id) => `/cases/${id}` },
  CONTRACT: { label: "Contract", className: "bg-indigo-950 text-indigo-300", href: (id) => `/contracts/${id}` },
  DOCUMENT: { label: "Document", className: "bg-slate-800 text-slate-300", href: () => `/documents` },
  RESEARCH: { label: "Research", className: "bg-emerald-950 text-emerald-300", href: (id) => `/research/${id}` },
  LAW: { label: "Law (public)", className: "bg-amber-950 text-amber-300", href: () => `/knowledge` },
};

export function SearchView() {
  const { workspaceId } = useAuth();
  const params = useSearchParams();
  const q = params.get("q") ?? "";

  const searchQuery = useQuery({
    queryKey: ["search", "global", workspaceId, q],
    queryFn: () => searchGlobal(workspaceId!, q),
    enabled: !!workspaceId && !!q,
  });

  if (!workspaceId) {
    return <div className="p-8 text-sm text-slate-500">Select a workspace to search.</div>;
  }
  if (!q) {
    return <div className="p-8 text-sm text-slate-500">Enter a search term.</div>;
  }

  return (
    <div className="mx-auto max-w-3xl p-8">
      <h1 className="text-2xl font-semibold">Search: &ldquo;{q}&rdquo;</h1>

      {searchQuery.isLoading && <p className="mt-4 text-sm text-slate-500">Searching…</p>}
      {searchQuery.isError && <p className="mt-4 text-sm text-red-400">Search failed.</p>}
      {searchQuery.data?.results.length === 0 && <p className="mt-4 text-sm text-slate-500">No results.</p>}

      <ul className="mt-6 space-y-2">
        {searchQuery.data?.results.map((r) => {
          const meta = TYPE_LABEL[r.type];
          return (
            <li key={`${r.type}-${r.id}`} className="rounded border border-slate-800 p-3 text-sm">
              <div className="flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${meta.className}`}>
                  {meta.label}
                </span>
                <Link href={meta.href(r.id)} className="font-medium text-slate-200 hover:underline">
                  {r.title}
                </Link>
              </div>
              {r.subtitle && <div className="mt-1 text-slate-500">{r.subtitle}</div>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
