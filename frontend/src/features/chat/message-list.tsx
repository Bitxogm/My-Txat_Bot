import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import type { UiMessage } from './use-chat';

const STATUS_NOTE: Partial<Record<UiMessage['status'], string>> = {
  stopped: 'Respuesta detenida.',
  error: 'No se pudo completar la respuesta.',
};

export function MessageList({ messages }: { messages: UiMessage[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [messages]);

  return (
    <div
      ref={containerRef}
      role="log"
      aria-live="polite"
      aria-label="Conversación"
      className="flex-1 overflow-y-auto"
    >
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6">
        {messages.length === 0 ? (
          <p className="text-muted-foreground mt-24 text-center text-sm">
            Escribe un mensaje para empezar.
          </p>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              aria-label={message.role === 'user' ? 'Tú' : 'Asistente'}
              className={cn(
                'flex flex-col gap-1',
                message.role === 'user' ? 'items-end' : 'items-start',
              )}
            >
              <div
                className={cn(
                  'max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed break-words whitespace-pre-wrap',
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-foreground',
                )}
              >
                {message.content ||
                  (message.status === 'streaming' ? (
                    <span className="text-muted-foreground animate-pulse" aria-label="Generando">
                      …
                    </span>
                  ) : null)}
              </div>
              {STATUS_NOTE[message.status] && (
                <span
                  className={cn(
                    'px-2 text-xs',
                    message.status === 'error' ? 'text-destructive' : 'text-muted-foreground',
                  )}
                >
                  {STATUS_NOTE[message.status]}
                </span>
              )}
            </article>
          ))
        )}
      </div>
    </div>
  );
}
