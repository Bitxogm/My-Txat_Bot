import { RotateCwIcon, WifiOffIcon } from 'lucide-react';
import { ThemeToggle } from '@/components/theme-toggle';
import { Button } from '@/components/ui/button';

/** Shown instead of the app when the server can't be reached: never stale data. */
export function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  const noNetwork = typeof navigator !== 'undefined' && navigator.onLine === false;
  return (
    <main className="relative flex min-h-svh flex-col items-center justify-center gap-4 p-6 text-center">
      <ThemeToggle className="absolute top-3 right-3" />
      <WifiOffIcon className="text-muted-foreground size-10" aria-hidden />
      <div className="flex flex-col gap-1">
        <h1 className="font-heading text-lg font-semibold">Sin conexión con el servidor</h1>
        <p className="text-muted-foreground max-w-sm text-sm">
          {noNetwork
            ? 'Este dispositivo no tiene red. Se reintentará al recuperarla.'
            : 'El servidor de Txat_bot no responde. Comprueba que está encendido y que estás en la red de casa o en Tailscale.'}
        </p>
      </div>
      <Button variant="outline" onClick={onRetry}>
        <RotateCwIcon />
        Reintentar
      </Button>
    </main>
  );
}
