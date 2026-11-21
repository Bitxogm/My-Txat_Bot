import { ApiError, fallbackMessage, isAbortError, kindFromStatus } from './errors';

export const API_BASE = '/api';
const REQUEST_ID_HEADER = 'X-Request-ID';

type UnauthorizedHandler = (error: ApiError) => void;

let onUnauthorized: UnauthorizedHandler | null = null;

/** Registers what to do on any 401 (e.g. redirect to login). Returns an unsubscribe function. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): () => void {
  onUnauthorized = handler;
  return () => {
    if (onUnauthorized === handler) onUnauthorized = null;
  };
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  accept?: string;
}

interface ErrorBody {
  error: { code: string; message: string; request_id: string };
}

function isErrorBody(value: unknown): value is ErrorBody {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const error: unknown = value.error;
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message' in error &&
    typeof error.message === 'string'
  );
}

export async function toApiError(response: Response): Promise<ApiError> {
  const kind = kindFromStatus(response.status);
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Not JSON (e.g. a proxy error page): fall back to a generic message.
  }
  const error = isErrorBody(body) ? body.error : null;
  return new ApiError({
    kind,
    status: response.status,
    code: error?.code ?? `HTTP_${response.status}`,
    message: error?.message ?? fallbackMessage(kind),
    requestId: error?.request_id ?? response.headers.get(REQUEST_ID_HEADER),
  });
}

export function networkError(): ApiError {
  return new ApiError({
    kind: 'network',
    status: null,
    code: 'NETWORK_ERROR',
    message: fallbackMessage('network'),
    requestId: null,
  });
}

/** Sends a request and returns the raw Response if it is 2xx; throws ApiError otherwise. */
export async function send(path: string, options: RequestOptions = {}): Promise<Response> {
  const { method = 'GET', body, signal, accept = 'application/json' } = options;
  const headers: Record<string, string> = { Accept: accept };
  // FormData (uploads): the browser sets the multipart Content-Type with its boundary.
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      credentials: 'same-origin',
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw networkError();
  }

  if (!response.ok) {
    const apiError = await toApiError(response);
    if (apiError.kind === 'unauthorized') onUnauthorized?.(apiError);
    throw apiError;
  }
  return response;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
