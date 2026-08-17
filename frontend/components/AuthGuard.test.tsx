import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import * as authHook from "@/hooks/useAuth";
import { AuthGuard } from "./AuthGuard";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: replaceMock }),
}));

function mockAuth(isAuthenticated: boolean) {
  vi.spyOn(authHook, "useAuth").mockReturnValue({
    isAuthenticated,
    token: isAuthenticated ? "tok" : null,
    workspaceId: null,
    user: null,
    isLoadingUser: false,
    userError: null,
    login: vi.fn(),
    logout: vi.fn(),
    selectWorkspace: vi.fn(),
  } as unknown as ReturnType<typeof authHook.useAuth>);
}

describe("AuthGuard — hydration-safe auth check", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    replaceMock.mockClear();
  });

  it("renders children once mounted and authenticated, never redirects", () => {
    mockAuth(true);
    render(
      <AuthGuard>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.getByText("Protected content")).toBeInTheDocument();
    expect(replaceMock).not.toHaveBeenCalled();
  });

  it("renders nothing and redirects to /login when not authenticated", () => {
    mockAuth(false);
    render(
      <AuthGuard>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(replaceMock).toHaveBeenCalledWith("/login");
  });
});
