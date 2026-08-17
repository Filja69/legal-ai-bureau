import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as legalApi from "@/api/legal";
import * as contractsApi from "@/api/contracts";
import * as researchApi from "@/api/research";
import * as authHook from "@/hooks/useAuth";
import DashboardPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("DashboardPage — root render", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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

  it("composes AuthGuard + sidebar + header + the Assistant home when authenticated", () => {
    render(<DashboardPage />, { wrapper });
    // Sidebar (RU nav) and Assistant composer both present — the full shell rendered, not a bare page.
    expect(screen.getAllByText("Главная").length).toBeGreaterThan(0);
    expect(screen.getByText("Чем помочь?")).toBeInTheDocument();
    expect(screen.getByLabelText("Открыть меню")).toBeInTheDocument();
  });
});
