import { useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from 'react';
import { PaperclipIcon, SendHorizontalIcon, SquareIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { AttachmentChip } from './attachment-chip';
import { ACCEPTED_EXTENSIONS, MAX_ATTACHMENTS, type PendingFile } from './use-attachments';

interface ComposerProps {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled: boolean;
  files?: PendingFile[];
  isUploading?: boolean;
  /** Omit to hide the attach button. */
  onAttach?: (files: File[]) => void;
  onRemoveFile?: (key: string) => void;
  /** Shown above the input when there are files (e.g. they will leave the network). */
  filesNote?: string | null;
}

export function Composer({
  onSend,
  onStop,
  isStreaming,
  disabled,
  files = [],
  isUploading = false,
  onAttach,
  onRemoveFile,
  filesNote = null,
}: ComposerProps) {
  const [draft, setDraft] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const canSend = !disabled && !isStreaming && !isUploading && draft.trim() !== '';
  const canAttach = !disabled && !isStreaming && files.length < MAX_ATTACHMENTS;

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

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files ?? []);
    event.target.value = ''; // picking the same file again must fire change again
    if (selected.length > 0) onAttach?.(selected);
  }

  return (
    <form onSubmit={handleSubmit} className="bg-background border-t">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-2 px-4 py-3">
        {files.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <ul aria-label="Ficheros adjuntos" className="flex flex-wrap gap-1.5">
              {files.map((file) => (
                <li key={file.key}>
                  <AttachmentChip
                    filename={file.filename}
                    sizeBytes={file.size_bytes}
                    uploading={file.attachment === null}
                    onRemove={onRemoveFile ? () => onRemoveFile(file.key) : undefined}
                  />
                </li>
              ))}
            </ul>
            {filesNote && <p className="text-muted-foreground text-xs">{filesNote}</p>}
          </div>
        )}
        <div className="flex items-end gap-2">
          {onAttach && (
            <>
              <input
                ref={fileInput}
                type="file"
                multiple
                accept={ACCEPTED_EXTENSIONS.join(',')}
                onChange={handleFiles}
                className="hidden"
                data-testid="file-input"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-lg"
                onClick={() => fileInput.current?.click()}
                disabled={!canAttach}
                aria-label="Adjuntar ficheros"
                title="Adjuntar ficheros (texto o PDF)"
              >
                <PaperclipIcon />
              </Button>
            </>
          )}
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
      </div>
    </form>
  );
}
