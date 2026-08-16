import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { clearAuth } from "@/lib/auth-store";
import * as authApi from "@/api/auth";
import { useAuth } from "./useAuth";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useAuth login workspace auto-selection", () => {
  beforeEach(() => {
    clearAuth();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("auto-selects the workspace when the user has exactly one membership", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue({ access_token: "tok", token_type: "bearer", expires_in_minutes: 60 });
    vi.spyOn(authApi, "fetchCurrentUser").mockResolvedValue({
      user_id: "u1",
      email: "a@b.com",
      name: "A",
      is_dev_bypass: false,
      memberships: [{ workspace_id: "ws-1", workspace_name: "Only WS", role: "member" }],
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login("a@b.com", "pw");
    });

    await waitFor(() => expect(result.current.workspaceId).toBe("ws-1"));
  });

  it("does NOT silently pick a workspace when the user has multiple memberships", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue({ access_token: "tok", token_type: "bearer", expires_in_minutes: 60 });
    vi.spyOn(authApi, "fetchCurrentUser").mockResolvedValue({
      user_id: "u1",
      email: "a@b.com",
      name: "A",
      is_dev_bypass: false,
      memberships: [
        { workspace_id: "ws-1", workspace_name: "First", role: "member" },
        { workspace_id: "ws-2", workspace_name: "Second", role: "member" },
      ],
    });

    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await result.current.login("a@b.com", "pw");
    });

    expect(result.current.workspaceId).toBeNull();
  });
});
