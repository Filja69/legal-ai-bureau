import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as authHook from "@/hooks/useAuth";
import LoginPage from "./page";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

function mockAuth(overrides: Partial<ReturnType<typeof authHook.useAuth>> = {}) {
  vi.spyOn(authHook, "useAuth").mockReturnValue({
    isAuthenticated: false,
    token: null,
    workspaceId: null,
    user: null,
    isLoadingUser: false,
    userError: null,
    login: vi.fn(),
    logout: vi.fn(),
    selectWorkspace: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof authHook.useAuth>);
}

describe("LoginPage — RU copy", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    replaceMock.mockClear();
  });

  it("renders the RU heading, labels, and disclaimer", () => {
    mockAuth();
    render(<LoginPage />);
    expect(screen.getByText("Legal AI Bureau")).toBeInTheDocument();
    expect(screen.getByText("Юридические исследования и анализ договоров")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Пароль")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
    expect(screen.getByText(/не заменяет/)).toBeInTheDocument();
  });

  it("shows the RU invalid-credentials message on a 401", async () => {
    const loginMock = vi.fn().mockRejectedValue(
      Object.assign(new Error("401"), { isAxiosError: true, response: { status: 401 } })
    );
    mockAuth({ login: loginMock });
    render(<LoginPage />);

    fireEvent.change(document.querySelector("input[type=email]")!, { target: { value: "a@b.com" } });
    fireEvent.change(document.querySelector("input[type=password]")!, { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => expect(screen.getByText("Неверный email или пароль.")).toBeInTheDocument());
  });

  it("redirects to /dashboard when already authenticated", () => {
    mockAuth({ isAuthenticated: true });
    render(<LoginPage />);
    expect(replaceMock).toHaveBeenCalledWith("/dashboard");
  });
});
