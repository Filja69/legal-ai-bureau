import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import * as authHook from "@/hooks/useAuth";
import { NavSidebar } from "./NavSidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("NavSidebar — mobile drawer", () => {
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

  it("renders nothing for the off-canvas drawer when mobileOpen is false", () => {
    render(<NavSidebar mobileOpen={false} onMobileClose={vi.fn()} />);
    expect(screen.queryByLabelText("Закрыть меню")).not.toBeInTheDocument();
  });

  it("renders all RU nav links in the drawer when mobileOpen is true", () => {
    render(<NavSidebar mobileOpen onMobileClose={vi.fn()} />);
    expect(screen.getByLabelText("Закрыть меню")).toBeInTheDocument();
    // Desktop sidebar renders the same link set too, so expect at least one of each.
    expect(screen.getAllByText("Главная").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Дела").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Договоры").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Исследования").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Документы").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Компании").length).toBeGreaterThan(0);
  });

  it("calls onMobileClose when a nav link inside the drawer is clicked", () => {
    const onMobileClose = vi.fn();
    render(<NavSidebar mobileOpen onMobileClose={onMobileClose} />);
    const closeButton = screen.getByLabelText("Закрыть меню");
    const drawerNav = closeButton.closest("nav")!;
    const casesLink = Array.from(drawerNav.querySelectorAll("a")).find((a) => a.textContent === "Дела")!;
    fireEvent.click(casesLink);
    expect(onMobileClose).toHaveBeenCalled();
  });

  it("calls onMobileClose when the backdrop is clicked", () => {
    const onMobileClose = vi.fn();
    render(<NavSidebar mobileOpen onMobileClose={onMobileClose} />);
    const closeButton = screen.getByLabelText("Закрыть меню");
    const overlay = closeButton.closest("nav")!.parentElement!;
    const backdrop = overlay.querySelector("[aria-hidden='true']")!;
    fireEvent.click(backdrop);
    expect(onMobileClose).toHaveBeenCalled();
  });

  it("calls onMobileClose via the drawer's own close (X) button", () => {
    const onMobileClose = vi.fn();
    render(<NavSidebar mobileOpen onMobileClose={onMobileClose} />);
    fireEvent.click(screen.getByLabelText("Закрыть меню"));
    expect(onMobileClose).toHaveBeenCalled();
  });

  it("drawer never renders collapsed/icon-only labels, even if the desktop sidebar is collapsed", () => {
    render(<NavSidebar mobileOpen onMobileClose={vi.fn()} />);
    const closeButton = screen.getByLabelText("Закрыть меню");
    const drawerNav = closeButton.closest("nav")!;
    const casesLink = Array.from(drawerNav.querySelectorAll("a")).find((a) => a.getAttribute("href") === "/cases")!;
    expect(casesLink.textContent).toBe("Дела");
  });
});
