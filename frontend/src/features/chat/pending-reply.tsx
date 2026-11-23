import { useEffect, useState } from 'react';

/** A local model can take a minute to load into the GPU before its first word. */
export const MODEL_LOADING_DELAY_MS = 3000;
export const MODEL_LOADING_NOTE = 'Cargando el modelo en memoria…';

/** What an assistant reply shows before its first token. */
export function PendingReply({ localModel }: { localModel: boolean }) {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!localModel) return;
    const timer = setTimeout(() => setSlow(true), MODEL_LOADING_DELAY_MS);
    return () => clearTimeout(timer);
  }, [localModel]);

  if (localModel && slow) {
    return (
      <span className="text-muted-foreground animate-pulse" role="status">
        {MODEL_LOADING_NOTE}
      </span>
    );
  }
  return (
    <span className="text-muted-foreground animate-pulse" aria-label="Generando">
      …
    </span>
  );
}
