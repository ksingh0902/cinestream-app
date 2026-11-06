import { apiClient } from '../../api/client';

export interface CatalogueStats {
  total_titles?: number;
  total_movies?: number;
  total_series?: number;
  sources?: Record<string, number>;
  [key: string]: any;
}

export interface SyncStatus {
  is_running?: boolean;
  status?: string;
  last_sync?: string | number;
  items_added?: number;
  message?: string;
  [key: string]: any;
}

export interface SystemHealth {
  ok: boolean;
  catalogue: string;
  time: number;
}

function getCsrfTokenFromCookie(): string {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)cinemymovies_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function fetchStats(): Promise<CatalogueStats> {
  return apiClient.get<CatalogueStats>('/api/stats');
}

export async function fetchSyncStatus(): Promise<SyncStatus> {
  return apiClient.get<SyncStatus>('/api/sync/status');
}

export async function triggerCatalogSync(): Promise<{ ok: boolean; message: string }> {
  const csrf = getCsrfTokenFromCookie();
  const formData = new FormData();
  if (csrf) formData.append('csrf_token', csrf);

  return apiClient.post<{ ok: boolean; message: string }>('/api/sync/latest', formData);
}

export async function fetchHealth(): Promise<SystemHealth> {
  return apiClient.get<SystemHealth>('/api/health');
}

export async function changeViewerPassword(
  currentAdminPassword: string,
  newViewerPassword: string
): Promise<{ success: boolean; message: string }> {
  const csrf = getCsrfTokenFromCookie();
  const formData = new URLSearchParams();
  formData.append('current_admin_password', currentAdminPassword);
  formData.append('new_viewer_password', newViewerPassword);
  formData.append('csrf_token', csrf);

  const res = await fetch('/api/admin/change-viewer-password', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: formData.toString(),
  });

  if (res.ok || res.status === 303 || res.redirected) {
    return { success: true, message: 'Viewer password updated and active viewer sessions revoked.' };
  }
  return { success: false, message: `Update failed with status ${res.status}` };
}

export async function signOutAllViewers(
  currentAdminPassword: string
): Promise<{ success: boolean; message: string }> {
  const csrf = getCsrfTokenFromCookie();
  const formData = new URLSearchParams();
  formData.append('current_admin_password', currentAdminPassword);
  formData.append('csrf_token', csrf);

  const res = await fetch('/api/admin/sign-out-viewers', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: formData.toString(),
  });

  if (res.ok || res.status === 303 || res.redirected) {
    return { success: true, message: 'All viewer sessions terminated successfully.' };
  }
  return { success: false, message: `Action failed with status ${res.status}` };
}

