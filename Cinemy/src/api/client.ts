import { ApiError } from './types';

export const DEFAULT_REQUEST_TIMEOUT_MS = 15000;

interface RequestOptions extends RequestInit {
  skipAuthRedirect?: boolean;
  timeoutMs?: number;
}

export async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const {
    skipAuthRedirect = false,
    timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
    signal: callerSignal,
    ...fetchOptions
  } = options;

  const defaultHeaders: Record<string, string> = {
    Accept: 'application/json',
  };

  // Only set Content-Type if body is not FormData or already set
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  const controller = new AbortController();
  let timedOut = false;

  const onCallerAbort = () => {
    controller.abort();
  };

  if (callerSignal) {
    if (callerSignal.aborted) {
      controller.abort();
    } else {
      callerSignal.addEventListener('abort', onCallerAbort, { once: true });
    }
  }

  const timeoutId =
    timeoutMs > 0
      ? setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, timeoutMs)
      : null;

  const config: RequestInit = {
    credentials: 'include',
    ...fetchOptions,
    signal: controller.signal,
    headers: {
      ...defaultHeaders,
      ...fetchOptions.headers,
    },
  };

  let response: Response;
  try {
    response = await fetch(endpoint, config);
  } catch (error: any) {
    if (timedOut) {
      throw new ApiError({
        status: 408,
        message: 'Request timed out. Please try again.',
        isTimeout: true,
        isNetworkError: true,
      });
    }
    if (controller.signal.aborted || error?.name === 'AbortError') {
      throw new ApiError({
        status: 0,
        message: 'Request was cancelled.',
        isAborted: true,
      });
    }
    throw new ApiError({
      status: 0,
      message: 'Network connection failure. Please check your internet connection.',
      isNetworkError: true,
    });
  } finally {
    if (timeoutId !== null) {
      clearTimeout(timeoutId);
    }
    if (callerSignal) {
      callerSignal.removeEventListener('abort', onCallerAbort);
    }
  }

  // Parse response body safely (handles empty or non-JSON responses)
  const contentType = response.headers.get('content-type') || '';
  let data: any = null;

  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch {
      data = null;
    }
  } else {
    try {
      data = await response.text();
    } catch {
      data = null;
    }
  }

  if (!response.ok) {
    const retryAfterHeader = response.headers.get('retry-after');
    const retryAfter = retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined;

    // Handle HTTP 401 (Unauthorized)
    if (response.status === 401 && !skipAuthRedirect) {
      const currentPath = window.location.pathname + window.location.search;
      // Prevent infinite redirect loops if already on login page
      if (!window.location.pathname.startsWith('/login')) {
        window.location.replace(`/login?next=${encodeURIComponent(currentPath)}`);
      }
    }

    const errorMessage =
      (typeof data === 'object' && data !== null && (data.detail || data.error || data.message)) ||
      (typeof data === 'string' && data.length < 200 ? data : null) ||
      `Request failed with status ${response.status}`;

    throw new ApiError({
      status: response.status,
      message: errorMessage,
      detail: typeof data === 'object' && data !== null ? data.detail : undefined,
      error: typeof data === 'object' && data !== null ? data.error : undefined,
      retryAfter,
    });
  }

  return data as T;
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestOptions) => request<T>(endpoint, { method: 'GET', ...options }),
  post: <T>(endpoint: string, body?: any, options?: RequestOptions) =>
    request<T>(endpoint, {
      method: 'POST',
      body: body instanceof FormData ? body : JSON.stringify(body),
      ...options,
    }),
};

