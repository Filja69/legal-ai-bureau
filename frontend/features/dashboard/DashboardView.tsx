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
import { Badge, Card, CardHeader } from "@/components/ui";

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
      <div className="flex min-h-full items-center justify-center bg-canvas p-8 text-sm text-muted">
        {user ? "Рабочее пространство не выбрано." : "Загрузка ваших рабочих пространств..."}
      </div>
    );
  }

  return (
    <div className="min-h-full bg-canvas">
      {/* --- Assistant composer: the primary, first-10-seconds surface --- */}
      <section className="mx-auto max-w-3xl px-4 pb-10 pt-12 text-center sm:px-6 sm:pt-16">
        <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Чем помочь?</h1>
        <p className="mt-3 text-base text-muted sm:text-lg">Опишите юридическую задачу или приложите документы</p>

        <div className="mt-8 rounded-2xl border border-line bg-white p-3 text-left shadow-panel sm:p-4">
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
            className="w-full resize-none border-0 bg-transparent p-2 text-base text-ink placeholder:text-slate-400 focus:outline-none"
          />
          <div className="flex items-center justify-between gap-2 border-t border-line px-2 pt-3">
            <button
              type="button"
              onClick={handleAttach}
              className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted hover:bg-panel-muted hover:text-ink"
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
              className="rounded-lg bg-brand px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-40"
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
              className="rounded-full border border-line bg-white px-3.5 py-1.5 text-sm text-slate-600 shadow-sm hover:border-blue-200 hover:bg-brand-soft hover:text-brand-strong"
            >
              {action.label}
            </Link>
          ))}
        </div>
      </section>

      {/* --- Existing operational data — same real signals, just secondary now --- */}
      <section className="mx-auto max-w-5xl px-4 pb-16 sm:px-6">
        <div className="flex items-center justify-between border-t border-line pt-6">
          <h2 className="text-sm font-semibold text-muted">Что у меня уже есть</h2>
          <span className="text-xs text-muted">
            Backend:{" "}
            <span className={healthStatus === "ok" ? "text-success" : "text-warning"}>
              {healthStatus === "ok" ? "работает" : healthStatus === "checking" ? "проверка…" : "недоступен"}
            </span>
          </span>
        </div>

        <Card className="mt-4">
          <CardHeader title="Требует внимания" />
          <ul className="space-y-1 text-sm text-slate-600">
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
                <Link href="/research" className="text-warning hover:underline">
                  {escalatedResearch.length} исследование(й) требуют проверки юристом
                </Link>
              </li>
            )}
            {unanalyzedContracts.length === 0 && lowConfidenceResearch.length === 0 && escalatedResearch.length === 0 && (
              <li className="text-muted">Сейчас ничего не требует внимания.</li>
            )}
          </ul>
        </Card>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader title="Активные дела" />
            {!casesQuery.data && <p className="text-sm text-muted">Загрузка…</p>}
            {casesQuery.data?.length === 0 && <p className="text-sm text-muted">Пока нет дел.</p>}
            <ul className="space-y-2">
              {casesQuery.data?.slice(0, 5).map((c) => (
                <li key={c.id} className="rounded-lg border border-line p-2.5 text-sm">
                  <Link href={`/cases/${c.id}`} className="font-medium text-ink hover:underline">
                    {c.title}
                  </Link>
                  <div className="text-muted">{c.status}</div>
                </li>
              ))}
            </ul>
            {casesQuery.data && casesQuery.data.length > 0 && (
              <Link href="/cases" className="mt-3 inline-block text-xs text-muted hover:underline">
                Все дела →
              </Link>
            )}
          </Card>

          <Card>
            <CardHeader title="Договоры" />
            {!contractsQuery.data && <p className="text-sm text-muted">Загрузка…</p>}
            {contractsQuery.data?.length === 0 && <p className="text-sm text-muted">Пока нет договоров.</p>}
            <ul className="space-y-2">
              {contractsQuery.data?.slice(0, 5).map((c) => (
                <li key={c.id} className="rounded-lg border border-line p-2.5 text-sm">
                  <Link href={`/contracts/${c.id}`} className="font-medium text-ink hover:underline">
                    {c.title}
                  </Link>
                  <div className="flex items-center gap-2 text-muted">
                    <span>
                      {c.contract_type} · {c.status}
                    </span>
                    {c.is_mock && <Badge tone="amber">MOCK</Badge>}
                  </div>
                </li>
              ))}
            </ul>
            {contractsQuery.data && contractsQuery.data.length > 0 && (
              <Link href="/contracts" className="mt-3 inline-block text-xs text-muted hover:underline">
                Все договоры →
              </Link>
            )}
          </Card>

          <Card>
            <CardHeader title="Последние исследования" />
            {!researchQuery.data && <p className="text-sm text-muted">Загрузка…</p>}
            {researchQuery.data?.items.length === 0 && <p className="text-sm text-muted">Пока нет исследований.</p>}
            <ul className="space-y-2">
              {researchQuery.data?.items.slice(0, 5).map((r) => (
                <li key={r.id} className="rounded-lg border border-line p-2.5 text-sm">
                  <Link href={`/research/${r.id}`} className="line-clamp-1 font-medium text-ink hover:underline">
                    {r.question}
                  </Link>
                  <div className="text-muted">{r.confidence} confidence</div>
                </li>
              ))}
            </ul>
            {researchQuery.data && researchQuery.data.items.length > 0 && (
              <Link href="/research" className="mt-3 inline-block text-xs text-muted hover:underline">
                Все исследования →
              </Link>
            )}
          </Card>
        </div>
      </section>
    </div>
  );
}
