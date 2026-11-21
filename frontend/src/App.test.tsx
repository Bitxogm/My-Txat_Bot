import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  getMe,
  listConversations,
  listModels,
  listPersonalities,
  login,
  logout,
  setUnauthorizedHandler,
  type ApiErrorKind,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

vi.mock('@/lib/notify-error', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/notify-error')>();
  return { notifyError: vi.fn(actual.notifyError) };
});
import { clearRuntimeCaches } from '@/pwa/caches';
import App from './App';

vi.mock('@/pwa/caches', () => ({ clearRuntimeCaches: vi.fn(async () => undefined) }));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getMe: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  listModels: vi.fn(),
  listConversations: vi.fn(),
  listPersonalities: vi.fn(),
  setUnauthorizedHandler: vi.fn(() => () => undefined),
}));
vi.mock('sonner', async (importOriginal) => ({
  ...(await importOriginal<typeof import('sonner')>()),
  toast: { info: vi.fn(), error: vi.fn() },
}));

function apiError(kind: ApiErrorKind, status: number | null, code: string, message: string) {
  return new ApiError({ kind, status, code, message, requestId: 'r' });
}

const unauthorized = () => apiError('unauthorized', 401, 'UNAUTHORIZED', 'Sesión no válida');

beforeEach(() => {
  vi.mocked(listModels).mockResolvedValue({ models: [], default_model: null });
  vi.mocked(listConversations).mockResolvedValue({ conversations: [] });
  vi.mocked(listPersonalities).mockResolvedValue({ personalities: [] });
});

afterEach(() => {
  vi.clearAllMocks();
});

async function fillLogin(password = 'secret-pass') {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('Usuario'), 'void');
  await user.type(screen.getByLabelText('Contraseña'), password);
  await user.click(screen.getByRole('button', { name: 'Entrar' }));
  return user;
}

describe('App auth flow', () => {
  it('shows the login form when there is no session, without an error toast', async () => {
    vi.mocked(getMe).mockRejectedValueOnce(unauthorized());

    render(<App />);

    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('goes straight to the chat with a valid session', async () => {
    vi.mocked(getMe).mockResolvedValueOnce({ username: 'void' });

    render(<App />);

    expect(await screen.findByRole('textbox', { name: 'Mensaje' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cerrar sesión (void)' })).toBeInTheDocument();
  });

  it('logs in and opens the chat', async () => {
    vi.mocked(getMe)
      .mockRejectedValueOnce(unauthorized())
      .mockResolvedValueOnce({ username: 'void' });
    vi.mocked(login).mockResolvedValueOnce(undefined);
    render(<App />);

    await fillLogin();

    expect(await screen.findByRole('textbox', { name: 'Mensaje' })).toBeInTheDocument();
    expect(login).toHaveBeenCalledWith({ username: 'void', password: 'secret-pass' });
  });

  it.each([
    [
      'invalid credentials',
      apiError('unauthorized', 401, 'INVALID_CREDENTIALS', 'Usuario o contraseña incorrectos'),
    ],
    [
      'lockout',
      apiError('rate_limited', 429, 'TOO_MANY_ATTEMPTS', 'Demasiados intentos fallidos.'),
    ],
    [
      'not configured',
      apiError('server', 503, 'AUTH_NOT_CONFIGURED', 'El login no está configurado'),
    ],
  ])('shows %s inline and clears the password', async (_name, failure) => {
    vi.mocked(getMe).mockRejectedValueOnce(unauthorized());
    vi.mocked(login).mockRejectedValueOnce(failure);
    render(<App />);

    await fillLogin();

    expect(await screen.findByRole('alert')).toHaveTextContent(failure.message);
    expect(screen.getByLabelText('Contraseña')).toHaveValue('');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('sends network failures to the toast', async () => {
    vi.mocked(getMe).mockRejectedValueOnce(unauthorized());
    const failure = apiError('network', null, 'NETWORK_ERROR', 'Sin conexión');
    vi.mocked(login).mockRejectedValueOnce(failure);
    render(<App />);

    await fillLogin();

    await waitFor(() => expect(notifyError).toHaveBeenCalledWith(failure));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('logs out', async () => {
    vi.mocked(getMe).mockResolvedValueOnce({ username: 'void' });
    vi.mocked(logout).mockResolvedValueOnce(undefined);
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión (void)' }));

    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument();
    expect(logout).toHaveBeenCalledOnce();
    expect(clearRuntimeCaches).toHaveBeenCalledOnce();
  });

  it('shows the offline screen instead of stale data and retries', async () => {
    vi.mocked(getMe)
      .mockRejectedValueOnce(apiError('network', null, 'NETWORK_ERROR', 'Sin conexión'))
      .mockResolvedValueOnce({ username: 'void' });
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText('Sin conexión con el servidor')).toBeInTheDocument();
    expect(notifyError).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Reintentar' }));

    expect(await screen.findByRole('textbox', { name: 'Mensaje' })).toBeInTheDocument();
  });

  it('retries by itself when the network comes back, and treats 502 as offline', async () => {
    vi.mocked(getMe)
      .mockRejectedValueOnce(apiError('server', 502, 'HTTP_502', 'Error del servidor'))
      .mockResolvedValueOnce({ username: 'void' });
    render(<App />);
    await screen.findByText('Sin conexión con el servidor');

    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    expect(await screen.findByRole('textbox', { name: 'Mensaje' })).toBeInTheDocument();
  });

  it('stays logged in and warns when logout fails on the server', async () => {
    vi.mocked(getMe).mockResolvedValueOnce({ username: 'void' });
    const failure = apiError('network', null, 'NETWORK_ERROR', 'Sin conexión');
    vi.mocked(logout).mockRejectedValueOnce(failure);
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión (void)' }));

    await waitFor(() => expect(notifyError).toHaveBeenCalledWith(failure));
    expect(screen.getByRole('textbox', { name: 'Mensaje' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Entrar' })).not.toBeInTheDocument();
  });

  it('logs out without an "expired" toast when the session was already gone', async () => {
    vi.mocked(getMe).mockResolvedValueOnce({ username: 'void' });
    vi.mocked(logout).mockImplementationOnce(() => {
      vi.mocked(setUnauthorizedHandler).mock.calls[0][0]?.(unauthorized());
      return Promise.reject(unauthorized());
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole('button', { name: 'Cerrar sesión (void)' }));

    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument();
    expect(toast.info).not.toHaveBeenCalled();
  });

  it('returns to the login form when the session expires', async () => {
    vi.mocked(getMe).mockResolvedValueOnce({ username: 'void' });
    render(<App />);
    await screen.findByRole('textbox', { name: 'Mensaje' });

    const handler = vi.mocked(setUnauthorizedHandler).mock.calls[0][0];
    act(() => handler?.(unauthorized()));

    expect(await screen.findByRole('button', { name: 'Entrar' })).toBeInTheDocument();
    expect(toast.info).toHaveBeenCalledWith('Tu sesión ha caducado. Vuelve a iniciar sesión.');
  });
});
