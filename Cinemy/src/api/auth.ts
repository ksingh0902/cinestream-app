import { apiClient } from './client';
import { AuthCheckResponse } from '../types/auth';

/**
 * Checks current session state using the existing FastAPI /api/auth/check endpoint.
 * skipAuthRedirect is enabled so unauthenticated status returns cleanly without triggering a 401 redirect loop.
 */
export async function checkAuth(): Promise<AuthCheckResponse> {
  return apiClient.get<AuthCheckResponse>('/api/auth/check', { skipAuthRedirect: true });
}

/**
 * Extracts the CSRF token from the non-HttpOnly cms_csrf cookie set by the server.
 */
export function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^| )cms_csrf=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Executes logout conforming to the existing backend contract.
 * Submits form-data to POST /logout with the existing cms_csrf token.
 */
export function performLogout(): void {
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/logout';

  const csrfToken = getCsrfToken();
  if (csrfToken) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = csrfToken;
    form.appendChild(input);
  }

  document.body.appendChild(form);
  form.submit();
}

