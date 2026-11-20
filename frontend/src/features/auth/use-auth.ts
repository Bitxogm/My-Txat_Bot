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
import { toast } from 'sonner';

export type AuthState =
  { status: 'checking' } | { status: 'anonymous' } | { status: 'authenticated'; username: string };

export interface UseAuth {
  state: AuthState;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
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

  useEffect(() => {
    const controller = new AbortController();
    getMe(controller.signal).then(
      ({ username }) => setState({ status: 'authenticated', username }),
      (error: unknown) => {
        if (isAbortError(error)) return;
        notifyError(error);
        setState({ status: 'anonymous' });
      },
    );
    return () => controller.abort();
  }, []);

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
    setState({ status: 'anonymous' });
  }, []);

  return { state, login, logout };
}
