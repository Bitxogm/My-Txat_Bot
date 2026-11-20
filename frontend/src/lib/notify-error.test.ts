import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import { notifyError } from './notify-error';

vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const toastError = vi.mocked(toast.error);

function apiError(kind: ApiError['kind'], requestId: string | null = 'rid-1') {
  return new ApiError({ kind, status: 500, code: 'X', message: 'Mensaje', requestId });
}

describe('notifyError', () => {
  beforeEach(() => {
    toastError.mockClear();
  });

  it('includes the request id for server errors', () => {
    notifyError(apiError('server'));

    expect(toastError).toHaveBeenCalledWith('Mensaje', {
      description: 'ID de la petición: rid-1',
    });
  });

  it('omits the request id for client errors', () => {
    notifyError(apiError('validation'));

    expect(toastError).toHaveBeenCalledWith('Mensaje', { description: undefined });
  });

  it('ignores aborted requests', () => {
    notifyError(new DOMException('aborted', 'AbortError'));

    expect(toastError).not.toHaveBeenCalled();
  });

  it('shows a generic message for unknown errors', () => {
    notifyError(new Error('boom'));

    expect(toastError).toHaveBeenCalledWith('Ha ocurrido un error inesperado.');
  });
});
