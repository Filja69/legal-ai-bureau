"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listCases } from "@/api/legal";
import { listContracts } from "@/api/contracts";
import { listResearchReports } from "@/api/research";
import { useAuth } from "@/hooks/useAuth";
import { useHealthCheck } from "@/hooks/useHealthCheck";

// UX iteration — "Legal AI Assistant" home. First-10-seconds redesign
// driven by real lawyer feedback: the old Dashboard opened straight onto
// dense operational data (cases/contracts/research grids), which read as
// "too complex" before a first-time user had done anything at all.
//
// The composer below is a HONEST ROUTING SHELL, not a new AI capability —
// there is no backend endpoint that takes free-text + files and decides
// what to do with them. Submitting the composer sends the text to the one
// existing surface that genuinely accepts a free-text legal question:
// POST /research (via the Legal Research page, prefilled via ?q=). The
// quick-action chips below it are plain navigation to the real, existing
// modules — Contracts / Documents / Research — nothing is faked, nothing
// claims to "understand" the request before a human (or the real,
// evidence-gated backend) actually looks at it. See
// docs/UX-ASSISTANT-ROUTING.md for exactly what forwards where and why.
//
// Existing dashboard data (attention items, active cases, contracts,
// recent research, backend health) is unchanged in substance — still only
// ever shows what the backend actually returned, no invented counts — just
// moved below the composer per the new information hierarchy: "what can I
// do here?" before "what do I already have?".

const QUICK_ACTIONS: { label: string; href: string; description: string }[] = [
  { label: "Проверить договор", href: "/contracts", description: "Загрузите договор и получите разбор рисков" },
  { label: "Разобрать документы по делу", href: "/documents", description: "Загрузите и проиндексируйте документы" },
  { label: "Провести юридическое исследование", href: "/research", description: "Задайте вопрос по законодательству" },
  { label: "Найти риски", href: "/contracts", description: "Анализ рисков — часть проверки договора" },
  { label: "Задать вопрос по документу", href: "/documents", description: "Откройте документ и используйте вкладку «Спросить»" },
];

export function DashboardView() {
  const healthStatus = useHealthCheck();
  const { workspaceId, user } = useAuth();
  const router = useRouter();
  const [task, setTask] = useState("");

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

  const unanalyzedContracts = contractsQuery.data?.filter((c) => c.status !== "analyzed" && c.status !== "analysis_failed") ?? [];
  const lowConfidenceResearch = researchQuery.data?.items.filter((r) => r.confidence === "low") ?? [];
  const escalatedResearch = researchQuery.data?.items.filter((r) => r.escalate_to_human) ?? [];

  function handleSend() {
    const trimmed = task.trim();
    if (!trimmed) return;
    // Honest routing: the only existing surface that accepts a free-text
    // legal question is Legal Research (real POST /research under the
    // hood) — never a fabricated "smart dispatcher".
    router.push(`/research?q=${encodeURIComponent(trimmed)}`);
  }

  function handleAttach() {
    // Honest routing: no cross-page file hand-off exists (and building one
    // just to feel smoother would be exactly the kind of fake orchestration
    // this iteration is required not to build) — attaching a document IS
    // going to the real, working Documents upload surface.
    router.push("/documents");
  }

  if (!workspaceId) {
    return (
      <div className="flex min-h-full items-center justify-center bg-white p-8 text-sm text-slate-500">
        {user ? "Рабочее пространство не выбрано." : "Загрузка ваших рабочих пространств..."}
      </div>
    );
  }

  return (
    <div className="min-h-full bg-gradient-to-b from-white to-slate-50">
      {/* --- Assistant composer: the primary, first-10-seconds surface --- */}
      <section className="mx-auto max-w-3xl px-4 pb-10 pt-12 text-center sm:px-6 sm:pt-16">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">Чем помочь?</h1>
        <p className="mt-3 text-base text-slate-500 sm:text-lg">Опишите юридическую задачу или приложите документы</p>

        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-3 text-left shadow-sm sm:p-4">
          <textarea
            value={task}
            onChange={(e) => setTask(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Например: проверь договор поставки, найди риски и предложи правки"
            rows={3}
            className="w-full resize-none border-0 bg-transparent p-2 text-base text-slate-900 placeholder:text-slate-400 focus:outline-none"
          />
          <div className="flex items-center justify-between gap-2 border-t border-slate-100 px-2 pt-3">
            <button
              type="button"
              onClick={handleAttach}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M11 5.5 6.5 10a2 2 0 1 1-2.83-2.83L8.5 2.34a3 3 0 1 1 4.24 4.24L7.9 11.4"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="hidden sm:inline">Прикрепить документ</span>
            </button>
            <button
              type="button"
              onClick={handleSend}
              disabled={!task.trim()}
              className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Отправить
            </button>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {QUICK_ACTIONS.map((action) => (
            <Link
              key={action.label}
              href={action.href}
              title={action.description}
              className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-sm text-slate-600 shadow-sm hover:border-indigo-200 hover:bg-indigo-50 hover:text-indigo-700"
            >
              {action.label}
            </Link>
          ))}
        </div>
      </section>

      {/* --- Existing operational data — same real signals, just secondary now --- */}
      <section className="mx-auto max-w-5xl px-4 pb-16 sm:px-6">
        <div className="flex items-center justify-between border-t border-slate-200 pt-6">
          <h2 className="text-sm font-semibold text-slate-400">Что у меня уже есть</h2>
          <span className="text-xs text-slate-400">
            Backend:{" "}
            <span className={healthStatus === "ok" ? "text-emerald-600" : "text-amber-600"}>
              {healthStatus === "ok" ? "работает" : healthStatus === "checking" ? "проверка…" : "недоступен"}
            </span>
          </span>
        </div>

        <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-700">Требует внимания</h3>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">
            {unanalyzedContracts.length > 0 && (
              <li>
                <Link href="/contracts" className="hover:underline">
                  {unanalyzedContracts.length} договор(ов) ожидают анализа
                </Link>
              </li>
            )}
            {lowConfidenceResearch.length > 0 && (
              <li>
                <Link href="/research" className="hover:underline">
                  {lowConfidenceResearch.length} исследование(й) с низкой уверенностью
                </Link>
              </li>
            )}
            {escalatedResearch.length > 0 && (
              <li>
                <Link href="/research" className="text-amber-600 hover:underline">
                  {escalatedResearch.length} исследование(й) требуют проверки юристом
                </Link>
              </li>
            )}
            {unanalyzedContracts.length === 0 && lowConfidenceResearch.length === 0 && escalatedResearch.length === 0 && (
              <li className="text-slate-400">Сейчас ничего не требует внимания.</li>
            )}
          </ul>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700">Активные дела</h3>
            {!casesQuery.data && <p className="mt-2 text-sm text-slate-400">Загрузка…</p>}
            {casesQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-400">Пока нет дел.</p>}
            <ul className="mt-2 space-y-2">
              {casesQuery.data?.slice(0, 5).map((c) => (
                <li key={c.id} className="rounded-lg border border-slate-100 p-2.5 text-sm">
                  <Link href={`/cases/${c.id}`} className="font-medium text-slate-800 hover:underline">
                    {c.title}
                  </Link>
                  <div className="text-slate-400">{c.status}</div>
                </li>
              ))}
            </ul>
            {casesQuery.data && casesQuery.data.length > 0 && (
              <Link href="/cases" className="mt-3 inline-block text-xs text-slate-400 hover:underline">
                Все дела →
              </Link>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700">Договоры</h3>
            {!contractsQuery.data && <p className="mt-2 text-sm text-slate-400">Загрузка…</p>}
            {contractsQuery.data?.length === 0 && <p className="mt-2 text-sm text-slate-400">Пока нет договоров.</p>}
            <ul className="mt-2 space-y-2">
              {contractsQuery.data?.slice(0, 5).map((c) => (
                <li key={c.id} className="rounded-lg border border-slate-100 p-2.5 text-sm">
                  <Link href={`/contracts/${c.id}`} className="font-medium text-slate-800 hover:underline">
                    {c.title}
                  </Link>
                  <div className="text-slate-400">
                    {c.contract_type} · {c.status}
                    {c.is_mock && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">MOCK</span>}
                  </div>
                </li>
              ))}
            </ul>
            {contractsQuery.data && contractsQuery.data.length > 0 && (
              <Link href="/contracts" className="mt-3 inline-block text-xs text-slate-400 hover:underline">
                Все договоры →
              </Link>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700">Последние исследования</h3>
            {!researchQuery.data && <p className="mt-2 text-sm text-slate-400">Загрузка…</p>}
            {researchQuery.data?.items.length === 0 && <p className="mt-2 text-sm text-slate-400">Пока нет исследований.</p>}
            <ul className="mt-2 space-y-2">
              {researchQuery.data?.items.slice(0, 5).map((r) => (
                <li key={r.id} className="rounded-lg border border-slate-100 p-2.5 text-sm">
                  <Link href={`/research/${r.id}`} className="line-clamp-1 font-medium text-slate-800 hover:underline">
                    {r.question}
                  </Link>
                  <div className="text-slate-400">{r.confidence} confidence</div>
                </li>
              ))}
            </ul>
            {researchQuery.data && researchQuery.data.items.length > 0 && (
              <Link href="/research" className="mt-3 inline-block text-xs text-slate-400 hover:underline">
                Все исследования →
              </Link>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}
