"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { ru } from "@/lib/copy";

const PRODUCT_SURFACES = [
  { href: "/dashboard", label: ru.nav.home },
  { href: "/cases", label: ru.nav.cases },
  { href: "/contracts", label: ru.nav.contracts },
  { href: "/research", label: ru.nav.research },
  { href: "/documents", label: ru.nav.documents },
  { href: "/companies", label: ru.nav.companies },
];

const ADMIN_SURFACES = [{ href: "/knowledge", label: ru.nav.knowledge }];

const ADMIN_ROLES = new Set(["admin", "owner"]);

interface NavSidebarProps {
  // UX iteration: on mobile this becomes an off-canvas drawer instead of
  // the always-visible desktop sidebar — state is owned by AppShell so
  // Header's hamburger button and this drawer agree on open/closed.
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function NavSidebar({ mobileOpen, onMobileClose }: NavSidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const { user, workspaceId, logout } = useAuth();

  const currentMembership = user?.memberships.find((m) => m.workspace_id === workspaceId);
  const isAdmin = user?.is_dev_bypass || (currentMembership && ADMIN_ROLES.has(currentMembership.role));

  function navBody(onNavigate?: () => void, forceExpanded = false) {
    const isCollapsed = forceExpanded ? false : collapsed;
    return (
      <>
        <ul className="flex-1 space-y-1 px-2">
          {PRODUCT_SURFACES.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onNavigate}
                  title={isCollapsed ? item.label : undefined}
                  className={`block truncate rounded px-2 py-1.5 text-sm ${
                    active ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"
                  }`}
                >
                  {isCollapsed ? item.label[0] : item.label}
                </Link>
              </li>
            );
          })}

          {isAdmin && (
            <>
              <li className="pt-3">
                {!isCollapsed && (
                  <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-600">
                    {ru.nav.adminSection}
                  </div>
                )}
              </li>
              {ADMIN_SURFACES.map((item) => {
                const active = pathname.startsWith(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      title={isCollapsed ? item.label : undefined}
                      className={`block truncate rounded px-2 py-1.5 text-sm ${
                        active ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"
                      }`}
                    >
                      {isCollapsed ? item.label[0] : item.label}
                    </Link>
                  </li>
                );
              })}
            </>
          )}
        </ul>

        <div className="border-t border-slate-800 p-3">
          {!isCollapsed && user && (
            <div className="mb-2 truncate text-xs text-slate-500">
              <div className="truncate text-slate-300">{user.email ?? "Dev identity"}</div>
              {currentMembership && <div>{currentMembership.role}</div>}
            </div>
          )}
          <Link
            href="/settings"
            onClick={onNavigate}
            title={ru.nav.settings}
            className={`block rounded px-2 py-1.5 text-sm ${pathname === "/settings" ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"}`}
          >
            {isCollapsed ? "⚙" : ru.nav.settings}
          </Link>
          <button
            onClick={logout}
            className="mt-1 w-full rounded px-2 py-1.5 text-left text-sm text-slate-400 hover:bg-slate-800/60"
          >
            {isCollapsed ? "⏻" : ru.nav.signOut}
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      {/* Desktop: always-visible sidebar, hidden below md */}
      <nav
        className={`hidden shrink-0 flex-col border-r border-slate-800 transition-all md:flex ${collapsed ? "w-14" : "w-56"}`}
      >
        <div className="flex items-center justify-between p-4">
          {!collapsed && <div className="text-sm font-semibold tracking-wide text-slate-400">{ru.nav.brand}</div>}
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
            aria-label={collapsed ? ru.nav.expand : ru.nav.collapse}
          >
            {collapsed ? "»" : "«"}
          </button>
        </div>
        {navBody()}
      </nav>

      {/* Mobile: off-canvas drawer, only rendered/interactive below md */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={onMobileClose} aria-hidden="true" />
          <nav className="relative flex w-64 max-w-[80vw] flex-col border-r border-slate-800 bg-slate-950">
            <div className="flex items-center justify-between p-4">
              <div className="text-sm font-semibold tracking-wide text-slate-400">{ru.nav.brand}</div>
              <button
                onClick={onMobileClose}
                className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
                aria-label={ru.nav.closeMenu}
              >
                ✕
              </button>
            </div>
            {navBody(onMobileClose, true)}
          </nav>
        </div>
      )}
    </>
  );
}
