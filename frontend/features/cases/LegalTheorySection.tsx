"use client";

import type { AppliedCaseLaw, AppliedRule, LegalTheory, UnverifiedAuthority } from "@/types/litigation";
import { Badge, Card, Checklist, ChecklistItem, Notice } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

// The five categories P2 requires be visually distinguishable at a glance.
// "legal_theory" is the ONLY one resting on an independently verified
// citation — everything else must read as visibly less certain, never as a
// confirmed legal conclusion.
const CLASSIFICATION_LABEL: Record<string, string> = {
  legal_theory: "Подтвержденная правовая теория",
  counsel_hypothesis: "Гипотеза юриста — не подтверждено",
  fact: "Факт",
  inference: "Вывод (инференция)",
};
const CLASSIFICATION_TONE: Record<string, BadgeTone> = {
  legal_theory: "green",
  counsel_hypothesis: "amber",
  fact: "blue",
  inference: "violet",
};

const STANCE_LABEL: Record<string, string> = {
  supports: "Подтверждает позицию",
  against: "Против позиции",
  distinguishable: "Отличимо от текущего дела",
  unclear: "Неясная позиция",
  unassessed: "Не охарактеризовано",
};
const STANCE_TONE: Record<string, BadgeTone> = {
  supports: "green",
  against: "red",
  distinguishable: "amber",
  unclear: "gray",
  unassessed: "gray",
};

function RuleCard({ rule }: { rule: AppliedRule }) {
  return (
    <details className="group rounded-xl border border-line bg-white p-3.5 open:pb-3.5">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{rule.citation}</span>
        <Badge tone={rule.verification_status === "verified" ? "green" : "amber"}>
          {rule.verification_status === "verified" ? "Проверено" : "Mock-источник"}
        </Badge>
      </summary>
      <div className="mt-2.5 space-y-2 border-t border-line pt-2.5">
        <p className="text-sm leading-relaxed text-slate-700">{rule.text}</p>
        <p className="text-xs text-muted">Источник: {rule.provenance}</p>
      </div>
    </details>
  );
}

function CaseLawCard({ decision }: { decision: AppliedCaseLaw }) {
  return (
    <details className="group rounded-xl border border-line bg-white p-3.5 open:pb-3.5">
      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">
          Дело № {decision.case_number}
          {decision.court_level_label && <span className="ml-2 font-normal text-muted">{decision.court_level_label}</span>}
        </span>
        <div className="flex items-center gap-1.5">
          <Badge tone={decision.verification_status === "verified" ? "green" : "amber"}>
            {decision.verification_status === "verified" ? "Проверено" : "Mock-источник"}
          </Badge>
          <Badge tone={STANCE_TONE[decision.stance] ?? "gray"}>{STANCE_LABEL[decision.stance] ?? decision.stance}</Badge>
        </div>
      </summary>
      <div className="mt-2.5 space-y-2 border-t border-line pt-2.5">
        <p className="text-sm leading-relaxed text-slate-700">{decision.text}</p>
        <div className="flex flex-wrap gap-3 text-xs text-muted">
          {decision.decision_date && <span>Дата: {decision.decision_date}</span>}
          {decision.outcome && <span>Исход: {decision.outcome}</span>}
          {decision.factual_similarity !== "unassessed" && <span>Фактическое сходство: {decision.factual_similarity}</span>}
          {decision.legal_issue_similarity !== "unassessed" && <span>Сходство правового вопроса: {decision.legal_issue_similarity}</span>}
        </div>
        {decision.distinguishing_facts.length > 0 && (
          <p className="text-xs text-muted">Отличающие обстоятельства: {decision.distinguishing_facts.join("; ")}</p>
        )}
      </div>
    </details>
  );
}

function UnverifiedAuthorityRow({ authority }: { authority: UnverifiedAuthority }) {
  return (
    <div className="rounded-xl border border-red-200 bg-danger-soft p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-ink">{authority.attempted_citation}</span>
        <Badge tone="red">Неподтвержденный источник</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-600">{authority.reason}</p>
    </div>
  );
}

function TheoryCard({ theory }: { theory: LegalTheory }) {
  const hasCaseLaw = theory.supporting_case_law.length + theory.adverse_case_law.length + theory.uncharacterized_case_law.length > 0;

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-ink">{theory.theory_name}</h3>
        <div className="flex items-center gap-1.5">
          <Badge tone={CLASSIFICATION_TONE[theory.classification] ?? "gray"}>
            {CLASSIFICATION_LABEL[theory.classification] ?? theory.classification}
          </Badge>
          <Badge tone="gray">Уверенность: {theory.confidence}</Badge>
        </div>
      </div>
      <p className="mt-1.5 text-xs text-muted">{theory.source_provenance}</p>

      {(theory.supporting_facts.length > 0 || theory.contradicting_facts.length > 0) && (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {theory.supporting_facts.length > 0 && (
            <div className="rounded-xl border border-line bg-panel-muted p-3">
              <div className="text-xs font-bold uppercase tracking-wide text-muted">Подтверждающие факты</div>
              <ul className="mt-1.5 space-y-1 text-sm text-slate-700">
                {theory.supporting_facts.map((f, i) => (
                  <li key={i}>• {f}</li>
                ))}
              </ul>
            </div>
          )}
          {theory.contradicting_facts.length > 0 && (
            <div className="rounded-xl border border-line bg-panel-muted p-3">
              <div className="text-xs font-bold uppercase tracking-wide text-muted">Противоречащие факты</div>
              <ul className="mt-1.5 space-y-1 text-sm text-slate-700">
                {theory.contradicting_facts.map((f, i) => (
                  <li key={i}>• {f}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {theory.reasoning && (
        <div className="mt-4 rounded-xl border border-line p-3">
          <div className="text-xs font-bold uppercase tracking-wide text-muted">Применение права к фактам</div>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{theory.reasoning}</p>
        </div>
      )}

      {theory.applicable_rules.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Применимые нормы права</div>
          <div className="space-y-2">
            {theory.applicable_rules.map((r) => (
              <RuleCard key={r.citation} rule={r} />
            ))}
          </div>
        </div>
      )}

      {hasCaseLaw && (
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {theory.supporting_case_law.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Подтверждающая практика</div>
              <div className="space-y-2">
                {theory.supporting_case_law.map((c) => (
                  <CaseLawCard key={c.case_number} decision={c} />
                ))}
              </div>
            </div>
          )}
          {theory.adverse_case_law.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Противоречащая / отличимая практика</div>
              <div className="space-y-2">
                {theory.adverse_case_law.map((c) => (
                  <CaseLawCard key={c.case_number} decision={c} />
                ))}
              </div>
            </div>
          )}
          {theory.uncharacterized_case_law.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Практика без оценки релевантности</div>
              <div className="space-y-2">
                {theory.uncharacterized_case_law.map((c) => (
                  <CaseLawCard key={c.case_number} decision={c} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {theory.unverified_authorities.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-danger">
            Неподтвержденные источники — не учтены в обосновании
          </div>
          <div className="space-y-2">
            {theory.unverified_authorities.map((u, i) => (
              <UnverifiedAuthorityRow key={i} authority={u} />
            ))}
          </div>
        </div>
      )}

      {theory.adverse_arguments.length > 0 && (
        <div className="mt-4 rounded-xl border border-line p-3">
          <div className="text-xs font-bold uppercase tracking-wide text-muted">Контраргументы (состязательный анализ)</div>
          <ul className="mt-1.5 space-y-1 text-sm text-slate-700">
            {theory.adverse_arguments.map((a, i) => (
              <li key={i}>• {a}</li>
            ))}
          </ul>
        </div>
      )}

      {theory.alternative_explanations.length > 0 && (
        <p className="mt-3 text-xs text-muted">Альтернативные объяснения: {theory.alternative_explanations.join("; ")}</p>
      )}

      {theory.evidence_gaps.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Недостающие доказательства</div>
          <Checklist>
            {theory.evidence_gaps.map((g, i) => (
              <ChecklistItem key={i}>
                <span className="font-medium text-ink">{g.missing_fact}</span> — {g.why_it_matters}
                <span className="block text-xs text-muted">
                  Может быть доказано: {g.could_be_proven_by}. Усилит теорию: {g.strengthens_theory_if_obtained}
                </span>
              </ChecklistItem>
            ))}
          </Checklist>
        </div>
      )}

      {theory.unresolved_legal_questions.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-muted">Нерешенные правовые вопросы</div>
          <Checklist>
            {theory.unresolved_legal_questions.map((q, i) => (
              <ChecklistItem key={i}>{q}</ChecklistItem>
            ))}
          </Checklist>
        </div>
      )}
    </Card>
  );
}

export function LegalTheorySection({ theories }: { theories: LegalTheory[] }) {
  if (theories.length === 0) {
    return <Notice tone="info">Правовые теории еще не сформированы для этого дела.</Notice>;
  }

  return (
    <div className="space-y-4">
      <Notice tone="info">
        Каждая теория помечена одной из категорий: факт, вывод, гипотеза юриста или подтвержденная правовая теория. Только
        последняя опирается на независимо проверенный источник права — остальные требуют дальнейшей проверки юристом.
      </Notice>
      {theories.map((t, i) => (
        <TheoryCard key={i} theory={t} />
      ))}
    </div>
  );
}
