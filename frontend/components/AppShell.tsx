"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import { Header } from "@/components/Header";
import { NavSidebar } from "@/components/NavSidebar";

// UX iteration: mobile nav is an off-canvas drawer, not the always-visible
// desktop sidebar — this is the one piece of state both Header (hamburger
// button) and NavSidebar (the drawer itself) need to share, so it lives
// here rather than in either component alone.
export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <NavSidebar mobileOpen={mobileNavOpen} onMobileClose={() => setMobileNavOpen(false)} />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header onMenuClick={() => setMobileNavOpen(true)} />
          <main className="min-w-0 flex-1 overflow-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
