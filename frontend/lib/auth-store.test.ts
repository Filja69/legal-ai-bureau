import { beforeEach, describe, expect, it } from "vitest";
import { clearAuth, getAuthState, setAuth, subscribeAuth } from "./auth-store";

describe("auth-store", () => {
  beforeEach(() => {
    clearAuth();
    window.sessionStorage.clear();
  });

  it("starts cleared", () => {
    expect(getAuthState()).toEqual({ token: null, workspaceId: null });
  });

  it("persists token and workspace across setAuth calls", () => {
    setAuth({ token: "abc" });
    setAuth({ workspaceId: "ws-1" });
    expect(getAuthState()).toEqual({ token: "abc", workspaceId: "ws-1" });
  });

  it("persists to sessionStorage, not localStorage", () => {
    setAuth({ token: "abc", workspaceId: "ws-1" });
    expect(window.sessionStorage.getItem("legal-ai-bureau.auth")).toContain("abc");
    expect(window.localStorage.getItem("legal-ai-bureau.auth")).toBeNull();
  });

  it("clearAuth wipes both state and storage", () => {
    setAuth({ token: "abc", workspaceId: "ws-1" });
    clearAuth();
    expect(getAuthState()).toEqual({ token: null, workspaceId: null });
    expect(window.sessionStorage.getItem("legal-ai-bureau.auth")).toBeNull();
  });

  it("notifies subscribers on change", () => {
    let calls = 0;
    const unsubscribe = subscribeAuth(() => calls++);
    setAuth({ token: "x" });
    expect(calls).toBe(1);
    unsubscribe();
    setAuth({ token: "y" });
    expect(calls).toBe(1);
  });
});
