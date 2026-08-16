import { apiClient } from "@/lib/api-client";
import type { CurrentUser, TokenResponse } from "@/types/auth";

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/api/v1/legal/auth/token", { email, password });
  return data;
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  const { data } = await apiClient.get<CurrentUser>("/api/v1/legal/auth/me");
  return data;
}
