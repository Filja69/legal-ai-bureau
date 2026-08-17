import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import * as authHook from "@/hooks/useAuth";
import { Header } from "./Header";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("Header — mobile hamburger", () => {
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
  });

  it("calls onMenuClick when the hamburger button is clicked", () => {
    const onMenuClick = vi.fn();
    render(<Header onMenuClick={onMenuClick} />);
    fireEvent.click(screen.getByLabelText("Открыть меню"));
    expect(onMenuClick).toHaveBeenCalled();
  });
});
