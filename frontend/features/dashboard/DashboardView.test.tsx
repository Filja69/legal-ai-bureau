import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as legalApi from "@/api/legal";
import * as contractsApi from "@/api/contracts";
import * as researchApi from "@/api/research";
import * as authHook from "@/hooks/useAuth";
import { DashboardView } from "./DashboardView";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("DashboardView — Legal AI Assistant home", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pushMock.mockClear();
    vi.spyOn(authHook, "useAuth").mockReturnValue({
      isAuthenticated: true,
      token: "tok",
      workspaceId: "ws-1",
      user: { user_id: "u1", email: "a@b.com", name: "A", is_dev_bypass: false, memberships: [] },
      isLoadingUser: false,
      userError: null,
      login: vi.fn(),
      logout: vi.fn(),
      selectWorkspace: vi.fn(),
    } as unknown as ReturnType<typeof authHook.useAuth>);
    vi.spyOn(legalApi, "checkHealth").mockResolvedValue({ status: "ok" });
    vi.spyOn(legalApi, "listCases").mockResolvedValue([]);
    vi.spyOn(contractsApi, "listContracts").mockResolvedValue([]);
    vi.spyOn(researchApi, "listResearchReports").mockResolvedValue({ total: 0, items: [] });
  });

  it("renders the RU composer heading and quick actions, not the old operational dashboard", () => {
    render(<DashboardView />, { wrapper });
    expect(screen.getByText("Чем помочь?")).toBeInTheDocument();
    expect(screen.getByText("Опишите юридическую задачу или приложите документы")).toBeInTheDocument();
    expect(screen.getByText("Проверить договор")).toBeInTheDocument();
    expect(screen.getByText("Разобрать документы по делу")).toBeInTheDocument();
    expect(screen.getByText("Провести юридическое исследование")).toBeInTheDocument();
    expect(screen.getByText("Найти риски")).toBeInTheDocument();
    expect(screen.getByText("Задать вопрос по документу")).toBeInTheDocument();
  });

  it("quick action chips are real links to existing modules, not fake AI dispatch", () => {
    render(<DashboardView />, { wrapper });
    expect(screen.getByText("Проверить договор").closest("a")).toHaveAttribute("href", "/contracts");
    expect(screen.getByText("Разобрать документы по делу").closest("a")).toHaveAttribute("href", "/documents");
    expect(screen.getByText("Провести юридическое исследование").closest("a")).toHaveAttribute("href", "/research");
  });

  it("composer Send routes free text to Legal Research via ?q=, never fabricates a result inline", () => {
    render(<DashboardView />, { wrapper });
    const textarea = screen.getByPlaceholderText(/проверь договор поставки/);
    fireEvent.change(textarea, { target: { value: "проверь договор поставки на риски" } });
    fireEvent.click(screen.getByText("Отправить"));
    expect(pushMock).toHaveBeenCalledWith("/research?q=" + encodeURIComponent("проверь договор поставки на риски"));
  });

  it("Send is disabled for empty input and never navigates", () => {
    render(<DashboardView />, { wrapper });
    expect(screen.getByText("Отправить")).toBeDisabled();
    fireEvent.click(screen.getByText("Отправить"));
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("attach button routes to the real Documents upload page, not a fake attach flow", () => {
    render(<DashboardView />, { wrapper });
    fireEvent.click(screen.getByText("Прикрепить документ"));
    expect(pushMock).toHaveBeenCalledWith("/documents");
  });

  it("still shows the real operational data section below the composer", () => {
    render(<DashboardView />, { wrapper });
    expect(screen.getByText("Что у меня уже есть")).toBeInTheDocument();
    expect(screen.getByText("Сейчас ничего не требует внимания.")).toBeInTheDocument();
  });
});
