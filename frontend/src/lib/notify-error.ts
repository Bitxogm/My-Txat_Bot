import { toast } from 'sonner';
import { ApiError, isAbortError } from '@/lib/api';

/**
 * Shows an error toast. Server and network errors include the request_id so it can be
 * looked up in the backend logs. Aborted requests are ignored.
 */
export function notifyError(error: unknown): void {
  if (isAbortError(error)) return;

  if (!(error instanceof ApiError)) {
    toast.error('Ha ocurrido un error inesperado.');
    return;
  }

  const showRequestId = (error.kind === 'server' || error.kind === 'network') && error.requestId;
  toast.error(error.message, {
    description: showRequestId ? `ID de la petición: ${error.requestId}` : undefined,
  });
}
