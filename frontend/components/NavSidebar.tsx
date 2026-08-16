"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";

const PRODUCT_SURFACES = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/cases", label: "Cases" },
  { href: "/contracts", label: "Contracts" },
  { href: "/research", label: "Legal Research" },
  { href: "/documents", label: "Documents" },
  { href: "/companies", label: "Companies" },
];

const ADMIN_SURFACES = [{ href: "/knowledge", label: "Knowledge" }];

const ADMIN_ROLES = new Set(["admin", "owner"]);

export function NavSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const { user, workspaceId, logout } = useAuth();

  const currentMembership = user?.memberships.find((m) => m.workspace_id === workspaceId);
  const isAdmin = user?.is_dev_bypass || (currentMembership && ADMIN_ROLES.has(currentMembership.role));

  return (
    <nav
      className={`flex shrink-0 flex-col border-r border-slate-800 transition-all ${collapsed ? "w-14" : "w-56"}`}
    >
      <div className="flex items-center justify-between p-4">
        {!collapsed && <div className="text-sm font-semibold tracking-wide text-slate-400">LEGAL AI BUREAU</div>}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="rounded p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-300"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "»" : "«"}
        </button>
      </div>

      <ul className="flex-1 space-y-1 px-2">
        {PRODUCT_SURFACES.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`block truncate rounded px-2 py-1.5 text-sm ${
                  active ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"
                }`}
              >
                {collapsed ? item.label[0] : item.label}
              </Link>
            </li>
          );
        })}

        {isAdmin && (
          <>
            <li className="pt-3">
              {!collapsed && <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-600">Admin</div>}
            </li>
            {ADMIN_SURFACES.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    title={collapsed ? item.label : undefined}
                    className={`block truncate rounded px-2 py-1.5 text-sm ${
                      active ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"
                    }`}
                  >
                    {collapsed ? item.label[0] : item.label}
                  </Link>
                </li>
              );
            })}
          </>
        )}
      </ul>

      <div className="border-t border-slate-800 p-3">
        {!collapsed && user && (
          <div className="mb-2 truncate text-xs text-slate-500">
            <div className="truncate text-slate-300">{user.email ?? "Dev identity"}</div>
            {currentMembership && <div>{currentMembership.role}</div>}
          </div>
        )}
        <Link
          href="/settings"
          title="Settings"
          className={`block rounded px-2 py-1.5 text-sm ${pathname === "/settings" ? "bg-slate-800 text-slate-100" : "text-slate-300 hover:bg-slate-800/60"}`}
        >
          {collapsed ? "⚙" : "Settings"}
        </Link>
        <button
          onClick={logout}
          className="mt-1 w-full rounded px-2 py-1.5 text-left text-sm text-slate-400 hover:bg-slate-800/60"
        >
          {collapsed ? "⏻" : "Sign out"}
        </button>
      </div>
    </nav>
  );
}
