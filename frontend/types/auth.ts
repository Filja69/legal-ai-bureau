// Mirrors backend/app/api/v1/auth.py

export interface WorkspaceMembership {
  workspace_id: string;
  workspace_name: string;
  role: string;
}

export interface CurrentUser {
  user_id: string;
  email: string | null;
  name: string | null;
  is_dev_bypass: boolean;
  memberships: WorkspaceMembership[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
}
