import axios from "axios";
import { clearAuth, getAuthState } from "@/lib/auth-store";

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8010",
  headers: {
    "Content-Type": "application/json",
  },
});

// Every request automatically carries the current bearer token and (if one
// is selected) the current workspace — callers no longer pass these by hand
// except when explicitly overriding withWorkspace() for a specific request.
apiClient.interceptors.request.use((config) => {
  const { token, workspaceId } = getAuthState();
  config.headers = config.headers ?? {};
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (workspaceId && !config.headers["X-Workspace-Id"]) config.headers["X-Workspace-Id"] = workspaceId;
  return config;
});

// A 401 means the token is missing/invalid/expired — never worth retrying
// silently. Clear it and let the auth guard (see AuthGuard.tsx) redirect to
// /login. We do NOT do this for 403 (authorization denied) — that's a real,
// displayable "you don't have access" state, not a session problem.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      clearAuth();
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

export function withWorkspace(workspaceId: string) {
  return { headers: { "X-Workspace-Id": workspaceId } };
}
