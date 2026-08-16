"use client";

import { useCallback, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCurrentUser, login as loginRequest } from "@/api/auth";
import { clearAuth, getAuthState, setAuth, subscribeAuth } from "@/lib/auth-store";

export function useAuth() {
  const [authState, setAuthState] = useState(getAuthState());
  const queryClient = useQueryClient();

  useEffect(() => subscribeAuth(() => setAuthState(getAuthState())), []);

  const meQuery = useQuery({
    queryKey: ["auth", "me", authState.token],
    queryFn: fetchCurrentUser,
    enabled: !!authState.token,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await loginRequest(email, password);
      setAuth({ token: access_token });
      const user = await fetchCurrentUser();
      // Auto-select the only workspace so a single-workspace user never has to
      // manually pick — but never silently guess for a user with more than
      // one, that's what the workspace selector is for.
      if (user.memberships.length === 1 && !getAuthState().workspaceId) {
        setAuth({ workspaceId: user.memberships[0].workspace_id });
      }
      queryClient.invalidateQueries({ queryKey: ["auth"] });
      return user;
    },
    [queryClient]
  );

  const logout = useCallback(() => {
    clearAuth();
    queryClient.clear();
  }, [queryClient]);

  const selectWorkspace = useCallback((workspaceId: string) => {
    setAuth({ workspaceId });
  }, []);

  return {
    isAuthenticated: !!authState.token,
    token: authState.token,
    workspaceId: authState.workspaceId,
    user: meQuery.data,
    isLoadingUser: meQuery.isLoading,
    userError: meQuery.error,
    login,
    logout,
    selectWorkspace,
  };
}
