"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listCases } from "@/api/legal";
import { listContracts } from "@/api/contracts";
import { listResearchReports } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import { useHealthCheck } from "@/hooks/useHealthCheck";

// Dashboard shows only what the backend actually returned — no invented
// counts, no fake percentages (Phase 8 brief §5/§25). An empty result
// renders "No X yet.", never a placeholder number.

export function DashboardView() {
  const healthStatus = useHealthCheck();
  const { workspaceId, user } = useAuth();

  const casesQuery = useQuery({
    queryKey: ["dashboard", "cases", workspaceId],
    queryFn: () => listCases(workspaceId!),
    enabled: !!workspaceId,
  });

  const contractsQuery = useQuery({
    queryKey: ["dashboard", "contracts", workspaceId],
    queryFn: () => listContracts(workspaceId!),
    enabled: !!workspaceId,
  });

  const researchQuery = useQuery({
    queryKey: ["dashboard", "research", workspaceId],
    queryFn: () => listResearchReports(workspaceId!, { limit: 10 }),
    enabled: !!workspaceId,
  });

  const analyzedContracts = contractsQuery.data?.filter((c) => c.status === "analyzed") ?? [];
  const unanalyzedContracts = contractsQuery.data?.filter((c) => c.status !== "analyzed" && c.status !== "analysis_failed") ?? [];
  const lowConfidenceResearch = researchQuery.data?.items.filter((r) => r.confidence === "low") ?? [];
  const escalatedResearch = researchQuery.data?.items.filter((r) => r.escalate_to_human) ?? [];

  if (!workspaceId) {
    return (
      <div className="p-8 text-sm text-slate-500">
        {user ? "No workspace selected." : "Loading your workspaces..."}
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <span className="text-xs text-slate-500">
          Backend: <span className={healthStatus === "ok" ? "text-emerald-400" : "text-amber-400"}>{healthStatus}</span>
        </span>
      </div>

      {/* Action items — only real, computed signals, never fabricated */}
      <section className="mt-6 rounded border border-slate-800 p-4">
        <h2 className="text-sm font-semibold text-slate-300">What needs attention</h2>
        <ul className="mt-2 space-y-1 text-sm text-slate-300">
          {unanalyzedContracts.length > 0 && (
            <li>
              <Link href="/contracts" className="hover:underline">
                {unanalyzedContracts.length} contract{unanalyzedContracts.length === 1 ? "" : "s"} awaiting analysis
              </Link>
            </li>
          )}
          {lowConfidenceResearch.length > 0 && (
            <li>
              <Link href="/research" className="hover:underline">
                {lowConfidenceResearch.length} research report{lowConfidenceResearch.length === 1 ? "" : "s"} with LOW confidence
              </Link>
            </li>
          )}
          {escalatedResearch.length > 0 && (
            <li>
              <Link href="/research" className="hover:underline text-amber-400">
                {escalatedResearch.length} research report{escalatedResearch.length === 1 ? "" : "s"} flagged for human review
              </Link>
            </li>
          )}
          {unanalyzedContracts.length === 0 && lowConfidenceResearch.length === 0 && escalatedResearch.length === 0 && (
            <li className="text-slate-500">Nothing needs attention right now.</li>
          )}
        </ul>
      </section>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section>
          <h2 className="text-sm font-semibold text-slate-300">Active Cases</h2>
          {!casesQuery.data && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
          {casesQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">No cases yet.</p>}
          <ul className="mt-2 space-y-2">
            {casesQuery.data?.slice(0, 5).map((c) => (
              <li key={c.id} className="rounded border border-slate-800 p-3 text-sm">
                <Link href={`/cases/${c.id}`} className="font-medium text-slate-200 hover:underline">
                  {c.title}
                </Link>
                <div className="text-slate-500">{c.status}</div>
              </li>
            ))}
          </ul>
          {casesQuery.data && casesQuery.data.length > 0 && (
            <Link href="/cases" className="mt-2 inline-block text-xs text-slate-500 hover:underline">
              View all cases →
            </Link>
          )}
        </section>

        <section>
          <h2 className="text-sm font-semibold text-slate-300">Contracts</h2>
          {!contractsQuery.data && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
          {contractsQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-500">No contracts yet.</p>}
          <ul className="mt-2 space-y-2">
            {contractsQuery.data?.slice(0, 5).map((c) => (
              <li key={c.id} className="rounded border border-slate-800 p-3 text-sm">
                <Link href={`/contracts/${c.id}`} className="font-medium text-slate-200 hover:underline">
                  {c.title}
                </Link>
                <div className="text-slate-500">
                  {c.contract_type} · {c.status}
                  {c.is_mock && <span className="ml-2 rounded bg-amber-900 px-1.5 py-0.5 text-[10px] text-amber-300">MOCK</span>}
                </div>
              </li>
            ))}
          </ul>
          {contractsQuery.data && contractsQuery.data.length > 0 && (
            <Link href="/contracts" className="mt-2 inline-block text-xs text-slate-500 hover:underline">
              View all contracts →
            </Link>
          )}
        </section>

        <section>
          <h2 className="text-sm font-semibold text-slate-300">Recent Research</h2>
          {!researchQuery.data && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
          {researchQuery.data?.items.length === 0 && <p className="mt-2 text-sm text-slate-500">No research yet.</p>}
          <ul className="mt-2 space-y-2">
            {researchQuery.data?.items.slice(0, 5).map((r) => (
              <li key={r.id} className="rounded border border-slate-800 p-3 text-sm">
                <Link href={`/research/${r.id}`} className="font-medium text-slate-200 hover:underline line-clamp-1">
                  {r.question}
                </Link>
                <div className="text-slate-500">{r.confidence} confidence</div>
              </li>
            ))}
          </ul>
          {researchQuery.data && researchQuery.data.items.length > 0 && (
            <Link href="/research" className="mt-2 inline-block text-xs text-slate-500 hover:underline">
              View all research →
            </Link>
          )}
        </section>
      </div>
    </div>
  );
}
