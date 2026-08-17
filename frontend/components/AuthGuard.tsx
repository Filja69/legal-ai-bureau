"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";

/** Wraps every authenticated page. No token -> /login. Token present but
 * /auth/me failed (expired/invalid, caught by the 401 interceptor which
 * already clears it) -> the isAuthenticated flip on the next render sends
 * us here anyway. This component owns navigation; it never renders a 401
 * itself.
 *
 * Bounded hydration fix (previously a known dev-mode warning on /cases,
 * see docs/PHASE-9-3-LITIGATION-RESULT.md §29.3): `useAuth()`'s token
 * comes from `lib/auth-store.ts`, a module-level variable that reads
 * `sessionStorage` the instant the module loads in the browser — before
 * React even starts hydrating. The server always renders `isAuthenticated
 * = false` (no storage on the server), but the client's very first render
 * could already see `true`, so React finds a mismatch. `mounted` forces
 * the first client render to match the server (render null either way),
 * then a `useEffect` (which only ever runs post-hydration) flips it to the
 * real value on the next tick — invisible to the user, no change to actual
 * auth logic, purely a render-timing fix.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (mounted && !isAuthenticated) router.replace("/login");
  }, [mounted, isAuthenticated, router]);

  if (!mounted || !isAuthenticated) return null;
  return <>{children}</>;
}
