"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/useAuth";

/** Wraps every authenticated page. No token -> /login. Token present but
 * /auth/me failed (expired/invalid, caught by the 401 interceptor which
 * already clears it) -> the isAuthenticated flip on the next render sends
 * us here anyway. This component owns navigation; it never renders a 401
 * itself.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated) router.replace("/login");
  }, [isAuthenticated, router]);

  if (!isAuthenticated) return null;
  return <>{children}</>;
}
