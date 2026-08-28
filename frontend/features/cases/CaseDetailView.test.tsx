import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as legalApi from "@/api/legal";
import * as litigationApi from "@/api/litigation";
import * as researchApi from "@/api/research";
import * as documentsApi from "@/api/documents";
import * as authHook from "@/hooks/useAuth";
import { CaseDetailView } from "./CaseDetailView";
import type { Case } from "@/types/legal";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function baseCase(overrides: Partial<Case> = {}): Case {
  return {
    id: "case-1", workspace_id: "ws-1", title: "Test Dispute", status: "open",
    client_name: "Client Co", counterparty_name: "Opponent Co", matter_type: "contract dispute",
    ...overrides,
  };
}

describe("CaseDetailView", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authHook, "useAuth").mockReturnValue({
      isAuthenticated: true, token: "tok", workspaceId: "ws-1", user: null,
      isLoadingUser: false, userError: null, login: vi.fn(), logout: vi.fn(), selectWorkspace: vi.fn(),
    } as unknown as ReturnType<typeof authHook.useAuth>);
    vi.spyOn(litigationApi, "listCaseDocuments").mockResolvedValue([]);
    vi.spyOn(researchApi, "listResearchReports").mockResolvedValue({ total: 0, items: [] });
    vi.spyOn(documentsApi, "listDocuments").mockResolvedValue([]);
  });

  it("shows a not-found message for a forbidden/missing case", async () => {
    vi.spyOn(legalApi, "getCase").mockRejectedValue(new Error("404"));
    render(<CaseDetailView caseId="case-x" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Case not found.")).toBeInTheDocument());
  });

  it("renders fact status badges with honest SUPPORTED/UNKNOWN labels, never fabricated", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "listCaseFacts").mockResolvedValue([
      {
        id: "f1", case_id: "case-1", statement: "Payment due 10.03.2026", fact_type: "date",
        status: "supported", normalized_value: "2026-03-10", created_at: null,
        evidence: [{ document_id: "d1", document_title: "Invoice", chunk_id: null, page_number: 1, section_path: null, excerpt: "…10.03.2026…" }],
      },
    ]);

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Dispute")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Facts" }));

    await waitFor(() => expect(screen.getByText("Payment due 10.03.2026")).toBeInTheDocument());
    expect(screen.getByText("supported")).toBeInTheDocument();
    expect(screen.getByText("Invoice")).toBeInTheDocument();
  });

  it("displays contradictions with both conflicting fact statements", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "getCaseEvidenceMatrix").mockResolvedValue([
      { fact_statement: "Amount 500000", fact_type: "amount", normalized_value: "500000.00", strength: "conflicted", reasons: ["Contradicted by another document in this case"], corroboration_count: 1 },
    ]);
    vi.spyOn(litigationApi, "listCaseContradictions").mockResolvedValue([
      {
        id: "c1", case_id: "case-1", contradiction_type: "amount_mismatch",
        description: "Documents disagree on an amount of similar magnitude: 500000.00 vs 450000.00",
        fact_a_id: "f1", fact_a_statement: "Amount 500000", fact_b_id: "f2", fact_b_statement: "Amount 450000",
      },
    ]);

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Dispute")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Evidence" }));

    await waitFor(() => expect(screen.getByText("amount mismatch")).toBeInTheDocument());
    expect(screen.getByText(/Amount 500000.*vs.*Amount 450000/)).toBeInTheDocument();
    expect(screen.getByText("conflicted")).toBeInTheDocument();
  });

  it("shows Strategy and Drafts as explicitly out of scope, never fabricated content", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Dispute")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Strategy" }));
    expect(screen.getByText(/explicitly out of scope/)).toBeInTheDocument();
  });

  it("shows the compact result-summary block on Overview with real data, and the KB warning", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "getCaseResultSummary").mockResolvedValue({
      case_snapshot: { party_names: [], document_count: 3, payment_count: 2, total_amount: "4000000.00", key_dates: [] },
      key_findings: [
        {
          severity: "HIGH",
          statement: "The payer itself referenced a specific loan agreement…",
          source_document_id: "d1", source_document_title: "payment_11.txt", page_number: 1,
          excerpt: "…займа от 11.09.2024…", confidence: "Based only on the documented evidence above.",
          caveat: "This evidence does not by itself establish that the contract was legally concluded.",
        },
      ],
      money_flow: { transaction_count: 2, transactions: [], total_amount: "4000000.00", referenced_contract_dates: {}, referenced_contract_numbers: {} },
      what_this_may_mean: ["Данные документы создают основание дополнительно проверять версию о существовании договорных отношений."],
      missing_critical_evidence: [
        {
          priority: "CRITICAL", description: "Подтверждённый подписанный экземпляр договора не обнаружен среди загруженных материалов.",
          why_it_matters: "…", source_document_id: null, source_document_title: null,
        },
      ],
      next_best_actions: [{ priority: 1, action: "Поднять переписку сторон за сентябрь 2024.", why: "…" }],
      legal_kb_warning: "Правовая квалификация пока ограничена: система выявила доказательственные факты и противоречия, но не подтверждает окончательную правовую позицию без проверенных норм права.",
      party_relationship_findings: [],
    });

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Главный вывод по делу")).toBeInTheDocument());

    expect(screen.getByText(/The payer itself referenced a specific loan agreement/)).toBeInTheDocument();
    expect(screen.getByText(/4000000\.00.*\(2 платеж\(ей\)\)/)).toBeInTheDocument();
    expect(screen.getByText(/Подтверждённый подписанный экземпляр договора не обнаружен/)).toBeInTheDocument();
    // Appears twice by design now: the "Главный вывод" summary and the ranked action-plan list.
    expect(screen.getAllByText(/Поднять переписку сторон/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Правовая квалификация пока ограничена/)).toBeInTheDocument();
  });

  it("leads the Overview tab with the Master Case Report one-pager and top findings", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "getCaseMasterReport").mockResolvedValue({
      one_pager: {
        case_position: "3 findings identified.", strongest_point: "Internal tension in claimant's pleading",
        biggest_risk: "No confirmed signed contract copy", money_at_stake: "4400000.00",
        top_arguments: ["Internal tension in claimant's pleading"], top_risks: ["No confirmed signed contract copy"],
        what_opponent_must_explain: [], what_court_likely_focuses_on: null,
        missing_p0_evidence: ["Correspondence discussing loan terms"], next_best_action: "Obtain correspondence around the transfer dates.",
      },
      case_map: { claimed_amounts: [], claim_dates: [], note: "" },
      findings: [
        {
          id: "claim_contradiction:theory:0", category: "claim_contradiction",
          title: "Internal tension between two propositions in the same pleading",
          statement: "The pleading asserts both 'payment_by_mistake' and 'future_contract_negotiations'.",
          supporting_facts: [], contradicting_facts: [], source_document_ids: [], source_document_titles: [],
          excerpts: [], page_numbers: [], helps_side: "client", hurts_side: "opponent", strength: "HIGH",
          confidence: "Deterministic.", legal_significance: "Invites scrutiny.", counterargument: null,
          response_to_counterargument: null, caveat: "A tension worth investigating, not a resolved inconsistency.",
          missing_evidence: [], recommended_action: null, verification_status: "document_supported",
          alternative_explanations: [], what_would_strengthen: [], what_would_weaken: [], legal_research_required: false,
          synthesizes: [],
        },
      ],
      burden_map: [], court_scenarios: [], opposing_party_questions: [], draft_response_structure: [],
      contract_version_matrix: [], money_flow: { transaction_count: 2, transactions: [], total_amount: "4400000.00", referenced_contract_dates: {}, referenced_contract_numbers: {} },
      legal_kb_warning: null,
    });

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Master Case Report — 30-second Case Position")).toBeInTheDocument());

    // Appears twice by design now: the hero KPI tile and the money-flow card total.
    expect(screen.getAllByText("4400000.00").length).toBeGreaterThan(0);
    // Appears twice by design now: the hero description and the "strongest argument" insight tile.
    expect(screen.getAllByText(/Internal tension in claimant's pleading/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Obtain correspondence around the transfer dates/)).toBeInTheDocument();
    // Appears twice by design: once in the prominent Critical/High findings list
    // (it's HIGH strength) and again in the dedicated Internal Contradictions section
    // (it's a claim_contradiction) — the same finding surfaced in two purposeful groupings.
    expect(screen.getAllByText(/asserts both 'payment_by_mistake'/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/A tension worth investigating/).length).toBeGreaterThan(0);
  });

  it("shows the party relationships block only when findings exist, with timing and open questions", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "getCaseResultSummary").mockResolvedValue({
      case_snapshot: { party_names: [], document_count: 1, payment_count: 0, total_amount: "0.00", key_dates: [] },
      key_findings: [],
      money_flow: { transaction_count: 0, transactions: [], total_amount: "0.00", referenced_contract_dates: {}, referenced_contract_numbers: {} },
      what_this_may_mean: [],
      missing_critical_evidence: [],
      next_best_actions: [],
      legal_kb_warning: null,
      party_relationship_findings: [
        {
          subject_name: "Директор Истца (синтетика)", related_party_name: "ООО «Ответчик — TEST»",
          relationship_type: "member", relationship_start: "2024-06-01", relationship_end: null,
          timing_note: "Дата возникновения связи: 2024-06-01. Это не устанавливает осведомлённость само по себе.",
          why_it_may_matter: "Может иметь значение для оценки осведомлённости и поведения соответствующей стороны.",
          what_is_still_needed: ["История ЕГРЮЛ (EGRUL history)", "Реестр участников"],
          verification_status: "unverified", source_document_id: null, source_document_title: null, source_excerpt: null,
        },
      ],
    });

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Связи сторон и обстоятельства, требующие проверки")).toBeInTheDocument());

    expect(screen.getByText(/Директор Истца \(синтетика\)/)).toBeInTheDocument();
    expect(screen.getByText(/ООО «Ответчик — TEST»/)).toBeInTheDocument();
    expect(screen.getByText(/Требует проверки: История ЕГРЮЛ/)).toBeInTheDocument();
  });

  it("Legal Theories tab runs on demand and distinguishes verified theory, unverified authority, and case-law stance", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "getCaseLegalTheories").mockResolvedValue([
      {
        theory_name: "Contract formation/performance through the conduct of the parties",
        classification: "legal_theory",
        supporting_facts: ["Repeated payments referencing the same draft agreement"],
        contradicting_facts: ["Draft agreement was never signed"],
        alternative_explanations: ["Payments could reflect an unrelated obligation"],
        evidence_gaps: [],
        verified_legal_authority: ["ст. 432 ГК РФ"],
        source_provenance: "Verified via LegalResearchEngine (research_id=r1): 1 verified citation(s).",
        confidence: "medium",
        additional_evidence_required: [],
        research_id: "r1",
        applicable_rules: [
          { citation: "ст. 432 ГК РФ", text: "ст. 432 ГК РФ: существенные условия договора", verification_status: "verified", provenance: "Проверено по Базе Знаний: статья найдена, источник официальный или лицензированный." },
        ],
        supporting_case_law: [
          {
            case_number: "А40-1/2024", text: "А40-1/2024: суд признал договор заключенным по факту исполнения", verification_status: "verified",
            court_level_label: "АС г. Москвы", decision_date: "2024-01-01", outcome: "granted", stance: "supports",
            factual_similarity: "high", legal_issue_similarity: "high", distinguishing_facts: [], remains_useful: true,
          },
        ],
        adverse_case_law: [
          {
            case_number: "А40-2/2024", text: "А40-2/2024: суд отказал в аналогичном требовании", verification_status: "verified",
            court_level_label: "АС г. Москвы", decision_date: "2023-05-01", outcome: "denied", stance: "against",
            factual_similarity: "medium", legal_issue_similarity: "high", distinguishing_facts: ["Другая сумма договора"], remains_useful: true,
          },
        ],
        uncharacterized_case_law: [],
        unverified_authorities: [
          { attempted_citation: "ст. 99999 ГК РФ", claim_type: "rule", reason: "Цитата упомянута в рассуждении, но не подтверждена независимой проверкой (CitationValidator) — не учитывается в обосновании правовой позиции." },
        ],
        reasoning: "Повторяющиеся платежи со ссылкой на один и тот же проект договора указывают на его исполнение сторонами.",
        adverse_arguments: ["ст. 1102 ГК РФ: платежи могут быть неосновательным обогащением, если договор не был заключен"],
        unresolved_legal_questions: ["Была ли договоренность впоследствии оформлена нотариально?"],
      },
      {
        theory_name: "Alternative hypothesis with no legal authority found",
        classification: "counsel_hypothesis",
        supporting_facts: [], contradicting_facts: [], alternative_explanations: [], evidence_gaps: [],
        verified_legal_authority: [], source_provenance: "LegalResearchEngine found no verified legal authority for this question. Fails closed.",
        confidence: "low", additional_evidence_required: [], research_id: "r2",
        applicable_rules: [], supporting_case_law: [], adverse_case_law: [], uncharacterized_case_law: [],
        unverified_authorities: [], reasoning: "", adverse_arguments: [], unresolved_legal_questions: [],
      },
    ]);

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Dispute")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Legal Theories" }));

    expect(litigationApi.getCaseLegalTheories).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Запустить правовой анализ" }));

    await waitFor(() => expect(screen.getByText("Contract formation/performance through the conduct of the parties")).toBeInTheDocument());
    expect(screen.getByText("Подтвержденная правовая теория")).toBeInTheDocument();
    expect(screen.getByText("Гипотеза юриста — не подтверждено")).toBeInTheDocument();
    expect(screen.getByText("ст. 99999 ГК РФ")).toBeInTheDocument();
    expect(screen.getByText("Неподтвержденный источник")).toBeInTheDocument();
    expect(screen.getByText(/Дело № А40-1\/2024/)).toBeInTheDocument();
    expect(screen.getByText(/Дело № А40-2\/2024/)).toBeInTheDocument();
    expect(screen.getByText("Подтверждает позицию")).toBeInTheDocument();
    expect(screen.getByText("Против позиции")).toBeInTheDocument();
  });

  it("timeline shows event date type badges (EXACT vs UNKNOWN)", async () => {
    vi.spyOn(legalApi, "getCase").mockResolvedValue(baseCase());
    vi.spyOn(litigationApi, "getCaseTimeline").mockResolvedValue([
      { id: "e1", case_id: "case-1", event_date: "2026-03-10", date_type: "exact", description: "Delivery", event_type: "delivery", source_fact_id: "f1" },
    ]);

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Dispute")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Timeline" }));

    await waitFor(() => expect(screen.getByText("Delivery")).toBeInTheDocument());
    expect(screen.getByText("exact")).toBeInTheDocument();
  });
});
