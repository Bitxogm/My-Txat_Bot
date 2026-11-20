export type ApiErrorKind =
  | 'validation'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'payload_too_large'
  | 'rate_limited'
  | 'server'
  | 'network';

export interface ApiErrorInit {
  kind: ApiErrorKind;
  message: string;
  status: number | null;
  code: string;
  requestId: string | null;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly requestId: string | null;

  constructor({ kind, message, status, code, requestId }: ApiErrorInit) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export function kindFromStatus(status: number): ApiErrorKind {
  if (status === 400 || status === 422) return 'validation';
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 413) return 'payload_too_large';
  if (status === 429) return 'rate_limited';
  return 'server';
}

const FALLBACK_MESSAGES: Record<ApiErrorKind, string> = {
  validation: 'Los datos enviados no son válidos.',
  unauthorized: 'Tu sesión ha caducado. Vuelve a iniciar sesión.',
  forbidden: 'No tienes permiso para hacer esto.',
  not_found: 'No se ha encontrado el recurso.',
  payload_too_large: 'El fichero es demasiado grande.',
  rate_limited: 'Demasiadas peticiones. Espera un momento.',
  server: 'Error del servidor. Inténtalo de nuevo.',
  network: 'No se puede conectar con el servidor.',
};

export function fallbackMessage(kind: ApiErrorKind): string {
  return FALLBACK_MESSAGES[kind];
}

export function isAbortError(error: unknown): boolean {
  // Checked by name, not instanceof: DOMException may come from another realm (e.g. jsdom).
  return (
    typeof error === 'object' && error !== null && 'name' in error && error.name === 'AbortError'
  );
}
