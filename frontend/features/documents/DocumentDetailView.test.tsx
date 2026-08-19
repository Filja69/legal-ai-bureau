import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as contractsApi from "@/api/contracts";
import * as documentsApi from "@/api/documents";
import * as authHook from "@/hooks/useAuth";
import { DocumentDetailView } from "./DocumentDetailView";
import type { Document } from "@/types/document";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function baseDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: "doc-1",
    workspace_id: "ws-1",
    title: "Test Contract",
    document_type: "contract",
    original_filename: "test.txt",
    media_type: "text/plain",
    size_bytes: 100,
    sha256: "abc123",
    status: "ready",
    processing_error: null,
    created_at: "2026-01-01T00:00:00Z",
    processed_at: "2026-01-01T00:00:01Z",
    doc_metadata: { extractor: "txt", page_count: 1, chunk_count: 2, used_structure_detection: true, warnings: [] },
    ...overrides,
  };
}

describe("DocumentDetailView", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pushMock.mockReset();
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
  });

  it("shows a not-found message when the document is forbidden/missing (404)", async () => {
    vi.spyOn(documentsApi, "getDocument").mockRejectedValue(new Error("404"));
    render(<DocumentDetailView documentId="doc-x" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Document not found.")).toBeInTheDocument());
  });

  it("shows a Retry button for a failed document, and calls reprocess on click", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(
      baseDocument({ status: "failed", processing_error: "CORRUPTED_FILE: could not parse" })
    );
    const reprocessSpy = vi.spyOn(documentsApi, "reprocessDocument").mockResolvedValue(baseDocument({ status: "ready" }));

    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Retry Processing")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Retry Processing"));
    await waitFor(() => expect(reprocessSpy).toHaveBeenCalledWith("ws-1", "doc-1"));
  });

  it("shows OCR REQUIRED status with a Retry option, distinct from FAILED", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(
      baseDocument({ status: "ocr_required", processing_error: "This PDF has no extractable text layer." })
    );
    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("OCR REQUIRED")).toBeInTheDocument());
    expect(screen.getByText("Retry Processing")).toBeInTheDocument();
  });

  it("asking a question shows the insufficient-evidence message honestly, never a fabricated answer", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument());
    vi.spyOn(documentsApi, "askDocument").mockResolvedValue({
      status: "insufficient_document_evidence",
      answer: "",
      citations: [],
      answer_method: "llm",
    });

    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Contract")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    fireEvent.change(screen.getByPlaceholderText("Ask about this document"), { target: { value: "What is the term?" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit Question" }));

    await waitFor(() =>
      expect(screen.getByText("Insufficient document evidence to answer this question — nothing was fabricated.")).toBeInTheDocument()
    );
  });

  it("displays citations returned from Ask in the Citations tab", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument());
    vi.spyOn(documentsApi, "askDocument").mockResolvedValue({
      status: "answered",
      answer: "Payment is due within 10 days.",
      answer_method: "llm",
      citations: [
        {
          citation_type: "document_evidence",
          document_id: "doc-1",
          document_title: "Test Contract",
          page_number: 2,
          section_path: null,
          excerpt: "Payment due within 10 days of invoice.",
          label: "Test Contract, стр. 2",
          chunk_id: "chunk-1",
          content_hash: "abc123",
        },
      ],
    });

    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Contract")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    fireEvent.change(screen.getByPlaceholderText("Ask about this document"), { target: { value: "Payment terms?" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit Question" }));

    await waitFor(() => expect(screen.getByText("Payment is due within 10 days.")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Citations"));
    expect(screen.getByText("Test Contract, стр. 2")).toBeInTheDocument();
    expect(screen.getByText("DOCUMENT EVIDENCE")).toBeInTheDocument();
  });

  it("labels a deterministic extractive answer honestly, distinct from an LLM-reasoned one", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument());
    vi.spyOn(documentsApi, "askDocument").mockResolvedValue({
      status: "answered",
      answer: "В документе указана сумма к оплате: 500 000 руб.",
      answer_method: "extractive",
      citations: [
        {
          citation_type: "document_evidence_extracted",
          document_id: "doc-1",
          document_title: "Test Contract",
          page_number: null,
          section_path: null,
          excerpt: "Сумма к оплате составляет 500 000 руб.",
          label: "Test Contract",
          chunk_id: "chunk-1",
          content_hash: "abc123",
        },
      ],
    });

    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Contract")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    fireEvent.change(screen.getByPlaceholderText("Ask about this document"), {
      target: { value: "Какая сумма к оплате указана в документе?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Question" }));

    await waitFor(() => expect(screen.getByText("В документе указана сумма к оплате: 500 000 руб.")).toBeInTheDocument());
    expect(screen.getByText("Extracted")).toBeInTheDocument();
  });

  it("shows 'Отправить на проверку договора' for a READY document", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument({ status: "ready" }));
    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Отправить на проверку договора")).toBeInTheDocument());
  });

  it("does not offer contract creation for a non-READY document", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument({ status: "processing" }));
    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Test Contract")).toBeInTheDocument());
    expect(screen.queryByText("Отправить на проверку договора")).not.toBeInTheDocument();
  });

  it("clicking 'Отправить на проверку договора' calls createContract with the document_id and redirects", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument({ status: "ready", title: "Договор аренды" }));
    const createSpy = vi.spyOn(contractsApi, "createContract").mockResolvedValue({
      id: "contract-1",
      workspace_id: "ws-1",
      title: "Договор аренды",
      contract_type: "unknown",
      status: "draft",
      is_mock: false,
    });

    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Отправить на проверку договора")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Отправить на проверку договора"));

    await waitFor(() =>
      expect(createSpy).toHaveBeenCalledWith("ws-1", {
        title: "Договор аренды",
        contract_type: "unknown",
        document_id: "doc-1",
      })
    );
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/contracts/contract-1"));
  });

  it("shows an explicit error, never a silent failure, when contract creation fails", async () => {
    vi.spyOn(documentsApi, "getDocument").mockResolvedValue(baseDocument({ status: "ready" }));
    vi.spyOn(contractsApi, "createContract").mockRejectedValue(
      Object.assign(new Error("400"), {
        isAxiosError: true,
        response: { data: { detail: "Document has no extracted text to analyze" } },
      })
    );

    render(<DocumentDetailView documentId="doc-1" />, { wrapper });
    await waitFor(() => expect(screen.getByText("Отправить на проверку договора")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Отправить на проверку договора"));

    await waitFor(() => expect(screen.getByText("Document has no extracted text to analyze")).toBeInTheDocument());
    expect(pushMock).not.toHaveBeenCalled();
  });
});
