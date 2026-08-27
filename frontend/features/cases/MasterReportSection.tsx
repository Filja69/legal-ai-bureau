"use client";

import type { MasterCaseReport, MasterFinding } from "@/types/litigation";
import {
  Badge,
  Card,
  CardHeader,
  Checklist,
  ChecklistItem,
  CompareCard,
  Finding,
  HeroBanner,
  InsightTile,
  Kpi,
  KpiGrid,
  Notice,
  RankedItem,
  RankedList,
  ScenarioBlock,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

// Master Report finding "strength" is an evidentiary-importance scale
// (CRITICAL/HIGH/MEDIUM/LOW), not a helps/hurts-side judgment — colored by
// how much attention it deserves, not by whether it's good or bad news.
const STRENGTH_TONE: Record<string, BadgeTone> = { CRITICAL: "red", HIGH: "amber", MEDIUM: "blue", LOW: "gray" };
const STRENGTH_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

function byStrength(a: MasterFinding, b: MasterFinding) {
  return (STRENGTH_ORDER[a.strength] ?? 9) - (STRENGTH_ORDER[b.strength] ?? 9);
}

function SectionHeading({ title, description, count }: { title: string; description?: string; count?: number }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
      </div>
      {count !== undefined && <span className="shrink-0 text-xs font-medium text-muted">{count}</span>}
    </div>
  );
}

export function MasterReportSection({
  report,
  caseStatus,
  documentCount,
}: {
  report: MasterCaseReport;
  caseStatus: string;
  documentCount: number | undefined;
}) {
  const criticalHigh = report.findings.filter((f) => f.strength === "CRITICAL" || f.strength === "HIGH").sort(byStrength);
  const contradictions = report.findings.filter((f) => f.category === "claim_contradiction");
  const topArguments = report.findings.filter((f) => f.helps_side === "client").sort(byStrength);
  const worstRisks = report.findings
    .filter((f) => f.hurts_side === "client" || f.category === "risk" || f.category === "evidence_gap")
    .sort(byStrength);
  const keyContradiction = contradictions[0]?.title ?? null;

  const evidenceHitList = [
    ...report.one_pager.missing_p0_evidence.map((item) => ({ item, priority: true })),
    ...Array.from(new Set(report.findings.flatMap((f) => f.missing_evidence)))
      .filter((item) => !report.one_pager.missing_p0_evidence.includes(item))
      .map((item) => ({ item, priority: false })),
  ];

  return (
    <div className="space-y-5">
      <HeroBanner
        kicker="Позиция по делу"
        title={report.one_pager.case_position}
        description={report.one_pager.strongest_point ?? "Not identified yet."}
        badge={<Badge tone="blue">{caseStatus}</Badge>}
      >
        <KpiGrid>
          <Kpi label="Money at stake" value={report.one_pager.money_at_stake} />
          <Kpi label="Payments" value={report.money_flow.transaction_count} />
          <Kpi label="Documents" value={documentCount ?? "—"} />
          <Kpi label="Findings" value={report.findings.length} />
        </KpiGrid>
      </HeroBanner>

      {/* --- Executive Summary: the 30-second read --- */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <InsightTile label="Сильнейший аргумент" accent="green">
          {report.one_pager.strongest_point ?? "Не выявлен."}
        </InsightTile>
        <InsightTile label="Главный риск" accent="red">
          {report.one_pager.biggest_risk ?? "Не выявлен."}
        </InsightTile>
        <InsightTile label="Ключевое противоречие" accent="violet">
          {keyContradiction ?? "Не выявлено."}
        </InsightTile>
        <InsightTile label="Следующее действие" accent="blue">
          {report.one_pager.next_best_action ?? "Недостаточно данных."}
        </InsightTile>
      </div>

      {/* --- Critical/High findings: must jump out immediately --- */}
      {criticalHigh.length > 0 && (
        <Card>
          <SectionHeading title="Критичные и приоритетные выводы" description="Требуют внимания в первую очередь." count={criticalHigh.length} />
          <div className="space-y-2.5">
            {criticalHigh.map((f) => (
              <Finding
                key={f.id}
                title={f.title}
                badge={<Badge tone={STRENGTH_TONE[f.strength] ?? "gray"}>{f.strength}</Badge>}
                meta={[
                  ...f.source_document_titles.slice(0, 1).map((t) => (
                    <Badge key={t} tone="gray">
                      {t}
                    </Badge>
                  )),
                  f.legal_research_required && (
                    <Badge key="legal-research" tone="violet">
                      Требуется правовое исследование
                    </Badge>
                  ),
                  f.category === "synthesis" && f.synthesizes.length > 0 && (
                    <Badge key="synthesis" tone="blue">
                      Объединяет {f.synthesizes.length} вывод(ов)
                    </Badge>
                  ),
                ]}
              >
                {f.statement}
                {f.caveat && <div className="mt-1.5 text-xs text-muted">Caveat: {f.caveat}</div>}
                {f.alternative_explanations.length > 0 && (
                  <div className="mt-1.5 text-xs text-muted">
                    Альтернативные объяснения: {f.alternative_explanations.join("; ")}
                  </div>
                )}
              </Finding>
            ))}
          </div>
        </Card>
      )}

      {/* --- Internal Contradictions: claim vs evidence --- */}
      {contradictions.length > 0 && (
        <Card>
          <SectionHeading title="Внутренние противоречия" description="Утверждение против доказательства." count={contradictions.length} />
          <div className="space-y-2.5">
            {contradictions.map((f) => (
              <CompareCard
                key={f.id}
                title={f.title}
                badge={<Badge tone={STRENGTH_TONE[f.strength] ?? "gray"}>{f.strength}</Badge>}
                left={f.excerpts[0] ?? f.statement}
                right={f.excerpts[1] ?? "Источник не привязан к конкретному фрагменту."}
                caveat={f.caveat}
              />
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* --- Money Flow --- */}
        <Card>
          <CardHeader title="Денежный поток" description="Подтверждённые операции." action={<strong className="text-base text-ink">{report.money_flow.total_amount}</strong>} />
          <TableWrap>
            <thead>
              <tr>
                <Th>Дата</Th>
                <Th>Сумма</Th>
                <Th>Плательщик</Th>
                <Th>Основание</Th>
              </tr>
            </thead>
            <tbody>
              {report.money_flow.transactions.map((tx) => (
                <tr key={tx.payment_order_id}>
                  <Td>{tx.payment_date ?? "—"}</Td>
                  <Td>{tx.amount ?? "—"}</Td>
                  <Td>{tx.payer ?? "—"}</Td>
                  <Td>{tx.referenced_contract_date ? `Договор от ${tx.referenced_contract_date}` : "—"}</Td>
                </tr>
              ))}
              {report.money_flow.transactions.length === 0 && (
                <tr>
                  <Td className="text-muted">No transactions yet.</Td>
                </tr>
              )}
            </tbody>
          </TableWrap>
        </Card>

        {/* --- Contract Forensics --- */}
        {report.contract_version_matrix.length > 0 && (
          <Card>
            <CardHeader title="Договорная криминалистика" description="Сравнение версий договора." />
            <TableWrap>
              <thead>
                <tr>
                  <Th>Документ</Th>
                  <Th>Сумма</Th>
                  <Th>Ставка</Th>
                  <Th>Подпись</Th>
                </tr>
              </thead>
              <tbody>
                {report.contract_version_matrix.map((v) => (
                  <tr key={v.document_id}>
                    <Td className="text-ink">{v.document_title}</Td>
                    <Td>{v.amounts.length > 0 ? v.amounts.join(", ") : "—"}</Td>
                    <Td>{v.interest_rate ?? "—"}</Td>
                    <Td>
                      <Badge tone={v.signature_status === "signed" ? "green" : "amber"}>{v.signature_status}</Badge>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Card>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* --- Top Arguments --- */}
        {topArguments.length > 0 && (
          <Card>
            <SectionHeading title="Сильнейшие аргументы" description="Ранжировано по значимости." />
            <RankedList>
              {topArguments.map((f, i) => (
                <RankedItem key={f.id} rank={i + 1} title={f.title} badge={<Badge tone={STRENGTH_TONE[f.strength] ?? "gray"}>{f.strength}</Badge>}>
                  {f.statement}
                </RankedItem>
              ))}
            </RankedList>
          </Card>
        )}

        {/* --- Worst Risks --- */}
        {worstRisks.length > 0 && (
          <Card>
            <SectionHeading title="Наибольшие риски" description="Что может разрушить позицию." />
            <RankedList>
              {worstRisks.map((f, i) => (
                <RankedItem key={f.id} rank={i + 1} title={f.title} badge={<Badge tone={STRENGTH_TONE[f.strength] ?? "gray"}>{f.strength}</Badge>}>
                  {f.statement}
                </RankedItem>
              ))}
            </RankedList>
          </Card>
        )}
      </div>

      {/* --- Burden Map --- */}
      {report.burden_map.length > 0 && (
        <Card>
          <SectionHeading title="Карта бремени доказывания" description="Кто что должен доказать." />
          <TableWrap>
            <thead>
              <tr>
                <Th>Тезис</Th>
                <Th>Сторона</Th>
                <Th>Статус</Th>
                <Th>Слабость</Th>
              </tr>
            </thead>
            <tbody>
              {report.burden_map.map((b, i) => (
                <tr key={i}>
                  <Td className="text-ink">{b.proposition}</Td>
                  <Td className="text-muted">{b.side}</Td>
                  <Td>
                    <Badge tone={b.status === "contested" ? "amber" : "gray"}>{b.status}</Badge>
                  </Td>
                  <Td className="text-xs text-muted">{b.weakness ?? "—"}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </Card>
      )}

      {/* --- Evidence Hit List --- */}
      {evidenceHitList.length > 0 && (
        <Card>
          <SectionHeading title="Список недостающих доказательств" description="Что нужно получить, чтобы усилить позицию." count={evidenceHitList.length} />
          <Checklist>
            {evidenceHitList.map(({ item, priority }, i) => (
              <ChecklistItem key={i} badge={priority ? <Badge tone="red">P0</Badge> : undefined}>
                {item}
              </ChecklistItem>
            ))}
          </Checklist>
        </Card>
      )}

      {/* --- Court Scenarios --- */}
      {report.court_scenarios.length > 0 && (
        <Card>
          <SectionHeading title="Сценарии рассмотрения дела" description="Стратегические сценарии, не прогноз решения суда." />
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {report.court_scenarios.map((s, i) => (
              <ScenarioBlock key={i} label={s.label} scenario={s.scenario} why={s.why_court_could_get_there} supporting={s.facts_supporting} against={s.facts_against} />
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* --- Draft Response Structure --- */}
        {report.draft_response_structure.length > 0 && (
          <Card>
            <SectionHeading title="Структура проекта отзыва" description="Черновая карта для юриста, не готовый документ." />
            <ol className="space-y-2.5">
              {report.draft_response_structure.map((s, i) => (
                <li key={i} className="rounded-xl border border-line bg-white p-3.5">
                  <div className="text-sm font-semibold text-ink">
                    {i + 1}. {s.section}
                  </div>
                  <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{s.argument}</p>
                  {s.caution && (
                    <div className="mt-2">
                      <Notice tone="warning">{s.caution}</Notice>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          </Card>
        )}

        {/* --- Questions for Opponent --- */}
        {report.opposing_party_questions.length > 0 && (
          <Card>
            <SectionHeading title="Вопросы оппоненту" count={report.opposing_party_questions.length} />
            <Checklist>
              {report.opposing_party_questions.map((q, i) => (
                <ChecklistItem key={i}>{q}</ChecklistItem>
              ))}
            </Checklist>
          </Card>
        )}
      </div>

      {report.legal_kb_warning && (
        <Card>
          <p className="text-xs leading-relaxed text-amber-700">{report.legal_kb_warning}</p>
        </Card>
      )}
    </div>
  );
}
