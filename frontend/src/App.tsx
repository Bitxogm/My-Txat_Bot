import { Toaster } from '@/components/ui/sonner';
import { LoginPage } from '@/features/auth/login-page';
import { useAuth } from '@/features/auth/use-auth';
import { ChatPage } from '@/features/chat/chat-page';

export default function App() {
  const { state, login, logout } = useAuth();

  return (
    <>
      {state.status === 'checking' ? (
        <main className="flex min-h-svh items-center justify-center" aria-busy="true">
          <span className="text-muted-foreground text-sm">Cargando…</span>
        </main>
      ) : state.status === 'anonymous' ? (
        <LoginPage onLogin={login} />
      ) : (
        <ChatPage username={state.username} onLogout={() => void logout()} />
      )}
      <Toaster richColors closeButton />
    </>
  );
}
