import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import type { ReactNode } from "react";
import * as contractsApi from "@/api/contracts";
import * as authHook from "@/hooks/useAuth";
import { ContractsView } from "./ContractsView";
import type { Contract } from "@/types/contract";

function baseContract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: "contract-1",
    workspace_id: "ws-1",
    title: "Test Contract",
    contract_type: "service",
    status: "draft",
    is_mock: false,
    ...overrides,
  };
}

describe("ContractsView", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authHook, "useAuth").mockReturnValue({
      isAuthenticated: true,
      token: "tok",
      workspaceId: "ws-1",
      user: null,
      isLoadingUser: false,
      userError: null,
      login: vi.fn(),
      logout: vi.fn(),
      selectWorkspace: vi.fn(),
    } as unknown as ReturnType<typeof authHook.useAuth>);
    vi.spyOn(contractsApi, "listContracts").mockResolvedValue([]);
  });

  it("no longer claims that PDF/DOCX is unsupported, and offers a file-upload path via Documents", async () => {
    render(<ContractsView />);
    await waitFor(() => expect(screen.getByText("Договоры")).toBeInTheDocument());

    expect(screen.queryByText(/PDF\/DOCX пока не поддерживается/i)).not.toBeInTheDocument();
    const link = screen.getByText("Загрузить договор (файл)");
    expect(link.closest("a")).toHaveAttribute("href", "/documents");
  });

  it("still supports the manual raw-text flow, calling createContract with raw_text", async () => {
    const createSpy = vi.spyOn(contractsApi, "createContract").mockResolvedValue(baseContract());
    render(<ContractsView />);
    await waitFor(() => expect(screen.getByText("Договоры")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("Название"), { target: { value: "Мой договор" } });
    fireEvent.change(screen.getByPlaceholderText("Вставьте текст договора"), { target: { value: "Текст договора" } });
    fireEvent.click(screen.getByText("Загрузить договор"));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith("ws-1", {
        title: "Мой договор",
        raw_text: "Текст договора",
        contract_type: "service",
      })
    );
  });

  it("lists existing contracts once loaded", async () => {
    vi.spyOn(contractsApi, "listContracts").mockResolvedValue([baseContract({ title: "Договор поставки" })]);
    render(<ContractsView />);
    await waitFor(() => expect(screen.getByText("Договор поставки")).toBeInTheDocument());
  });
});
