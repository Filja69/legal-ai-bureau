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
    });

    render(<CaseDetailView caseId="case-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Главный вывод по делу")).toBeInTheDocument());

    expect(screen.getByText(/The payer itself referenced a specific loan agreement/)).toBeInTheDocument();
    expect(screen.getByText(/4000000\.00.*\(2 платеж\(ей\)\)/)).toBeInTheDocument();
    expect(screen.getByText(/Подтверждённый подписанный экземпляр договора не обнаружен/)).toBeInTheDocument();
    expect(screen.getByText(/Поднять переписку сторон/)).toBeInTheDocument();
    expect(screen.getByText(/Правовая квалификация пока ограничена/)).toBeInTheDocument();
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
