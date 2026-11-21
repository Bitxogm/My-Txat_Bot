import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  getMe,
  isAbortError,
  login as apiLogin,
  logout as apiLogout,
  setUnauthorizedHandler,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import { clearRuntimeCaches } from '@/pwa/caches';
import { toast } from 'sonner';

export type AuthState =
  | { status: 'checking' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; username: string }
  /** The server can't be reached (no network, backend down): nothing stale is shown. */
  | { status: 'offline' };

export interface UseAuth {
  state: AuthState;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Checks the session again (after being offline). */
  retry: () => void;
}

/** No answer from the backend: network down, or nginx answering 502/503/504 for it. */
function isUnreachable(error: unknown): boolean {
  return error instanceof ApiError && (error.kind === 'network' || error.kind === 'server');
}

export function useAuth(): UseAuth {
  const [state, setState] = useState<AuthState>({ status: 'checking' });
  const statusRef = useRef(state.status);
  // While the user is logging out on purpose, a 401 is expected, not an "expired session".
  const loggingOutRef = useRef(false);

  useEffect(() => {
    statusRef.current = state.status;
  }, [state.status]);

  useEffect(
    () =>
      // Any 401 from the API means the session is gone (expired, logged out elsewhere, restart).
      setUnauthorizedHandler(() => {
        if (statusRef.current === 'authenticated' && !loggingOutRef.current) {
          toast.info('Tu sesión ha caducado. Vuelve a iniciar sesión.');
        }
        setState({ status: 'anonymous' });
      }),
    [],
  );

  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    setState({ status: 'checking' });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    getMe(controller.signal).then(
      ({ username }) => setState({ status: 'authenticated', username }),
      (error: unknown) => {
        if (isAbortError(error)) return;
        if (isUnreachable(error)) {
          setState({ status: 'offline' });
          return;
        }
        notifyError(error);
        setState({ status: 'anonymous' });
      },
    );
    return () => controller.abort();
  }, [attempt]);

  // Back online: check again by itself.
  useEffect(() => {
    if (state.status !== 'offline') return;
    window.addEventListener('online', retry);
    return () => window.removeEventListener('online', retry);
  }, [state.status, retry]);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin({ username, password });
    const me = await getMe();
    setState({ status: 'authenticated', username: me.username });
  }, []);

  const logout = useCallback(async () => {
    loggingOutRef.current = true;
    try {
      await apiLogout();
    } catch (error) {
      // 401: the session was already gone. Anything else: the server may still consider the
      // session valid (the httpOnly cookie can't be cleared from JS), so don't pretend it ended.
      if (!(error instanceof ApiError && error.kind === 'unauthorized')) {
        notifyError(error);
        return;
      }
    } finally {
      loggingOutRef.current = false;
    }
    await clearRuntimeCaches();
    setState({ status: 'anonymous' });
  }, []);

  return { state, login, logout, retry };
}
