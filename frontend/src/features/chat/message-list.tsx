import { lazy, Suspense, useEffect, useRef } from 'react';
import { ErrorBoundary } from '@/components/error-boundary';
import { cn } from '@/lib/utils';
import { AttachmentChip } from './attachment-chip';
import type { UiMessage } from './use-chat';

const STATUS_NOTE: Partial<Record<UiMessage['status'], string>> = {
  stopped: 'Respuesta detenida.',
  error: 'No se pudo completar la respuesta.',
};

// Loaded on demand: react-markdown + GFM + highlighting are ~75 kB gzipped, not needed to log in.
const Markdown = lazy(() =>
  import('./markdown/markdown').then((module) => ({ default: module.Markdown })),
);

function PlainText({ text }: { text: string }) {
  return <div className="whitespace-pre-wrap">{text}</div>;
}

const EMPTY_REPLY_NOTE = 'El modelo no devolvió ninguna respuesta.';

function noteFor(message: UiMessage): { text: string; isError: boolean } | null {
  const empty = message.role === 'assistant' && message.content.trim() === '';
  // Replies saved as "done" with no text (e.g. a reasoning model that ran out of length).
  if (empty && message.status === 'done') return { text: EMPTY_REPLY_NOTE, isError: true };
  const text = STATUS_NOTE[message.status];
  return text ? { text, isError: message.status === 'error' } : null;
}

export function MessageList({
  messages,
  loading = false,
}: {
  messages: UiMessage[];
  loading?: boolean;
}) {
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
        {loading ? (
          <p className="text-muted-foreground mt-24 text-center text-sm">Cargando conversación…</p>
        ) : messages.length === 0 ? (
          <p className="text-muted-foreground mt-24 text-center text-sm">
            Escribe un mensaje para empezar.
          </p>
        ) : (
          messages.map((message) => {
            const note = noteFor(message);
            const showBubble = message.content !== '' || message.status === 'streaming';
            return (
              <article
                key={message.id}
                aria-label={message.role === 'user' ? 'Tú' : 'Asistente'}
                className={cn(
                  'flex flex-col gap-1',
                  message.role === 'user' ? 'items-end' : 'items-start',
                )}
              >
                {message.attachments.length > 0 && (
                  <ul aria-label="Ficheros enviados" className="flex flex-wrap justify-end gap-1.5">
                    {message.attachments.map((file) => (
                      <li key={file.id}>
                        <AttachmentChip
                          filename={file.filename}
                          sizeBytes={file.size_bytes}
                          truncated={file.truncated}
                        />
                      </li>
                    ))}
                  </ul>
                )}
                {showBubble && (
                  <div
                    className={cn(
                      'rounded-2xl px-4 py-2 text-sm leading-relaxed break-words',
                      message.role === 'user'
                        ? 'bg-primary text-primary-foreground max-w-[85%] whitespace-pre-wrap'
                        : 'bg-muted text-foreground w-full max-w-full min-w-0',
                    )}
                  >
                    {!message.content ? (
                      <span className="text-muted-foreground animate-pulse" aria-label="Generando">
                        …
                      </span>
                    ) : message.role === 'assistant' ? (
                      // Model output is rendered as Markdown; user text stays literal.
                      // If the renderer throws (pathological nesting, chunk failed to load), this
                      // message falls back to plain text instead of blanking the whole app.
                      <ErrorBoundary fallback={<PlainText text={message.content} />}>
                        <Suspense fallback={<PlainText text={message.content} />}>
                          <Markdown content={message.content} />
                        </Suspense>
                      </ErrorBoundary>
                    ) : (
                      message.content
                    )}
                  </div>
                )}
                {note && (
                  <span
                    className={cn(
                      'px-2 text-xs',
                      note.isError ? 'text-destructive' : 'text-muted-foreground',
                    )}
                  >
                    {note.text}
                  </span>
                )}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
