export type UserRole = 'admin' | 'viewer';

export interface AuthSuccessResponse {
  authenticated: true;
  username: string;
  role: UserRole;
  auth_version?: number;
}

export interface AuthUnauthenticatedResponse {
  authenticated: false;
  error?: string;
  detail?: string;
}

export type AuthCheckResponse = AuthSuccessResponse | AuthUnauthenticatedResponse;

export interface AuthState {
  authenticated: boolean;
  username: string | null;
  role: UserRole | null;
  loading: boolean;
  error: string | null;
  isStorageOutage: boolean;
}

