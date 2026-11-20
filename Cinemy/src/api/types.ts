export * from '../types/auth';
export * from '../types/catalogue';

export interface ApiErrorPayload {
  status: number;
  message: string;
  detail?: string;
  error?: string;
  retryAfter?: number;
  isNetworkError?: boolean;
  isTimeout?: boolean;
  isAborted?: boolean;
}

export class ApiError extends Error {
  public status: number;
  public detail?: string;
  public retryAfter?: number;
  public isNetworkError: boolean;
  public isTimeout: boolean;
  public isAborted: boolean;

  constructor(payload: ApiErrorPayload) {
    super(payload.message);
    this.name = 'ApiError';
    this.status = payload.status;
    this.detail = payload.detail || payload.error;
    this.retryAfter = payload.retryAfter;
    this.isNetworkError = Boolean(payload.isNetworkError);
    this.isTimeout = Boolean(payload.isTimeout);
    this.isAborted = Boolean(payload.isAborted);
  }
}

