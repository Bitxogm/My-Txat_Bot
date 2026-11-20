import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { SendHorizontalIcon, SquareIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

interface ComposerProps {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled: boolean;
}

export function Composer({ onSend, onStop, isStreaming, disabled }: ComposerProps) {
  const [draft, setDraft] = useState('');
  const canSend = !disabled && !isStreaming && draft.trim() !== '';

  function submit() {
    if (!canSend) return;
    onSend(draft);
    setDraft('');
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter adds a line; ignore Enter while an IME is composing.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-background border-t">
      <div className="mx-auto flex w-full max-w-3xl items-end gap-2 px-4 py-3">
        <label htmlFor="composer" className="sr-only">
          Mensaje
        </label>
        <Textarea
          id="composer"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Elige un modelo para empezar' : 'Escribe un mensaje…'}
          disabled={disabled}
          rows={1}
          className="max-h-48 min-h-10 resize-none"
        />
        {isStreaming ? (
          <Button
            type="button"
            variant="outline"
            size="icon-lg"
            onClick={onStop}
            aria-label="Detener"
          >
            <SquareIcon />
          </Button>
        ) : (
          <Button type="submit" size="icon-lg" disabled={!canSend} aria-label="Enviar">
            <SendHorizontalIcon />
          </Button>
        )}
      </div>
    </form>
  );
}
