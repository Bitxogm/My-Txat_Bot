import { useEffect, useRef, useState, type ReactNode } from 'react';
import { CheckIcon, CopyIcon, TriangleAlertIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { copyText } from '@/lib/clipboard';
import { notifyError } from '@/lib/notify-error';
import { HIDDEN_MARKER, stripHidden } from './hidden-chars';

interface CodeBlockProps {
  /** Raw code, exactly as the model wrote it (what gets copied). */
  code: string;
  language: string | null;
  /** Highlighted rendering of the same code. */
  children: ReactNode;
}

export function CodeBlock({ code, language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function handleCopy() {
    try {
      // Hidden characters are already shown as ⟦U+…⟧ markers; strip any left as a last guard.
      await copyText(stripHidden(code));
    } catch (error) {
      notifyError(error);
      return;
    }
    setCopied(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="my-3 overflow-hidden rounded-lg border bg-[#0d1117] text-[#e6edf3]">
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-1 text-xs">
        <span className="max-w-[20ch] truncate font-mono text-white/60">{language ?? 'texto'}</span>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          className="text-white/70 hover:bg-white/10 hover:text-white"
          onClick={() => void handleCopy()}
          aria-label={copied ? 'Copiado' : 'Copiar código'}
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? 'Copiado' : 'Copiar'}
        </Button>
      </div>
      {code.includes(HIDDEN_MARKER) && (
        <p className="flex items-center gap-2 border-b border-white/10 bg-amber-500/15 px-3 py-1.5 text-xs text-amber-200">
          <TriangleAlertIcon className="size-3.5 shrink-0" />
          Este bloque traía caracteres de control ocultos. Se muestran como ⟦U+…⟧ y así se copian:
          revísalo antes de pegarlo en una terminal.
        </p>
      )}
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed">{children}</pre>
    </div>
  );
}
