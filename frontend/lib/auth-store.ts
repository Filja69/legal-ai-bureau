// Plain module-level auth store — deliberately NOT a React context, so the
// axios interceptor in api-client.ts (outside the React tree) can read the
// current token/workspace synchronously on every request. React components
// subscribe via the useAuth hook (hooks/useAuth.ts).
//
// Token storage: sessionStorage, not localStorage — scoped to the tab, gone
// on close. A JWT is a bearer credential; minimizing its persistence window
// matters more here than "stay logged in across restarts" convenience.

export interface AuthState {
  token: string | null;
  workspaceId: string | null;
}

const STORAGE_KEY = "legal-ai-bureau.auth";

function readInitialState(): AuthState {
  if (typeof window === "undefined") return { token: null, workspaceId: null };
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { token: null, workspaceId: null };
    const parsed = JSON.parse(raw) as AuthState;
    return { token: parsed.token ?? null, workspaceId: parsed.workspaceId ?? null };
  } catch {
    return { token: null, workspaceId: null };
  }
}

let state: AuthState = readInitialState();
const listeners = new Set<() => void>();

function persist() {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function notify() {
  for (const listener of listeners) listener();
}

export function getAuthState(): AuthState {
  return state;
}

export function setAuth(next: Partial<AuthState>) {
  state = { ...state, ...next };
  persist();
  notify();
}

export function clearAuth() {
  state = { token: null, workspaceId: null };
  if (typeof window !== "undefined") window.sessionStorage.removeItem(STORAGE_KEY);
  notify();
}

export function subscribeAuth(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
