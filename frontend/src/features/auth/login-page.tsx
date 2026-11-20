import { useRef, useState, type FormEvent } from 'react';
import { KeyRoundIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ApiError } from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import type { DevCredentials } from './dev-login';
import { DEV_LOGIN } from './dev-login';

interface LoginPageProps {
  onLogin: (username: string, password: string) => Promise<void>;
  /** Injectable for tests; defaults to the dev-only credentials from .env.local. */
  devLogin?: DevCredentials | null;
}

export function LoginPage({ onLogin, devLogin = DEV_LOGIN }: LoginPageProps) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // A ref, not state: two submits in the same tick would both see a stale `submitting`.
  const inFlight = useRef(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await onLogin(username, password);
    } catch (err) {
      setPassword('');
      // HTTP errors (bad credentials, lockout, not configured) are shown in the form;
      // network failures go to the toast with the request id.
      if (err instanceof ApiError && err.status !== null) setError(err.message);
      else notifyError(err);
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>
            <h1 className="font-heading text-lg font-semibold">Txat_bot</h1>
          </CardTitle>
          <CardDescription>Inicia sesión para continuar.</CardDescription>
        </CardHeader>
        <CardContent>
          {/* method="post" so credentials never end up in the URL if the JS handler ever fails. */}
          <form method="post" onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            <div className="flex flex-col gap-2">
              <Label htmlFor="username">Usuario</Label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                aria-invalid={error !== null}
                aria-describedby={error ? 'login-error' : undefined}
              />
            </div>
            {error && (
              <p id="login-error" role="alert" className="text-destructive text-sm">
                {error}
              </p>
            )}
            <Button type="submit" disabled={submitting || !username || !password}>
              {submitting ? 'Entrando…' : 'Entrar'}
            </Button>
          </form>
          {devLogin && (
            <button
              type="button"
              onClick={() => {
                setUsername(devLogin.username);
                setPassword(devLogin.password);
                setError(null);
              }}
              className="hover:bg-muted mt-4 flex w-full items-center gap-3 rounded-lg border border-dashed p-3 text-left"
            >
              <KeyRoundIcon className="text-muted-foreground size-4 shrink-0" />
              <span className="flex flex-col">
                <span className="text-sm font-medium">Acceso rápido · {devLogin.username}</span>
                <span className="text-muted-foreground text-xs">
                  Solo en desarrollo. Rellena usuario y contraseña.
                </span>
              </span>
            </button>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
