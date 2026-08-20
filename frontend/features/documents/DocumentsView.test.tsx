import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as documentsApi from "@/api/documents";
import * as authHook from "@/hooks/useAuth";
import { DocumentsView } from "./DocumentsView";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("DocumentsView", () => {
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
    vi.spyOn(documentsApi, "listDocuments").mockResolvedValue([]);
  });

  // P0 production regression: a real backend `detail` message (e.g. from
  // the storage-failure 503 fix) must reach the user, never the generic
  // "backend доступен?" fallback that made the original incident
  // impossible to diagnose from the UI alone.
  it("shows the real backend detail message on upload failure, not the generic connectivity fallback", async () => {
    vi.spyOn(documentsApi, "uploadDocument").mockRejectedValue(
      Object.assign(new Error("503"), {
        isAxiosError: true,
        response: { status: 503, data: { detail: "Сервис хранения документов временно недоступен — попробуйте позже." } },
      })
    );

    render(<DocumentsView />, { wrapper });
    await waitFor(() => expect(screen.getByText("Документы")).toBeInTheDocument());

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "loan.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Загрузить"));

    await waitFor(() =>
      expect(screen.getByText("Сервис хранения документов временно недоступен — попробуйте позже.")).toBeInTheDocument()
    );
    expect(screen.queryByText("Загрузка не удалась — backend доступен?")).not.toBeInTheDocument();
  });

  it("falls back to the generic connectivity message only when the backend gives no response at all", async () => {
    // A genuine network-level failure (real CORS block, DNS failure, no
    // response reached) — axios error with no `.response` at all. This is
    // the ONLY case the generic fallback should still cover.
    vi.spyOn(documentsApi, "uploadDocument").mockRejectedValue(
      Object.assign(new Error("Network Error"), { isAxiosError: true, response: undefined })
    );

    render(<DocumentsView />, { wrapper });
    await waitFor(() => expect(screen.getByText("Документы")).toBeInTheDocument());

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "loan.docx", { type: "text/plain" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Загрузить"));

    await waitFor(() => expect(screen.getByText("Загрузка не удалась — backend доступен?")).toBeInTheDocument());
  });
});
