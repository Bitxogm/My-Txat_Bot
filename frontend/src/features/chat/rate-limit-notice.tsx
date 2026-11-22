import { useEffect, useState } from 'react';
import { ClockIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface RateLimit {
  provider: string;
  /** When the provider accepts requests again (ms since epoch); null if it didn't say. */
  until: number | null;
}

interface RateLimitNoticeProps {
  limit: RateLimit;
  /** Local default model offered instead; null hides the button. */
  localModel: string | null;
  onUseLocal: () => void;
  disabled?: boolean;
}

function secondsLeft(until: number | null): number | null {
  return until === null ? null : Math.max(0, Math.ceil((until - Date.now()) / 1000));
}

/**
 * Shown when a provider hits its rate limit. The message stays in the composer; the model only
 * changes if the user presses the button (never on its own).
 */
export function RateLimitNotice({ limit, localModel, onUseLocal, disabled }: RateLimitNoticeProps) {
  const [left, setLeft] = useState(() => secondsLeft(limit.until));

  // A new limit remounts this component (key in the page), so the first value is always fresh.
  useEffect(() => {
    if (limit.until === null) return;
    const timer = window.setInterval(() => setLeft(secondsLeft(limit.until)), 1000);
    return () => window.clearInterval(timer);
  }, [limit.until]);

  const when =
    left === null
      ? 'Espera un poco.'
      : left > 0
        ? `Disponible en ${left} s.`
        : 'Ya puedes reintentar.';

  return (
    <div
      role="status"
      className="bg-muted flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs"
    >
      <ClockIcon className="text-muted-foreground size-4 shrink-0" aria-hidden />
      <span className="flex-1">
        Límite de <strong>{limit.provider}</strong> alcanzado. {when} Tu mensaje sigue abajo.
      </span>
      {localModel && (
        <Button size="sm" variant="outline" onClick={onUseLocal} disabled={disabled}>
          Responder ahora con {localModel}
        </Button>
      )}
    </div>
  );
}
