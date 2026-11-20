import { useEffect, useRef, useState, type ReactNode } from 'react';
import { CheckIcon, CopyIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { copyText } from '@/lib/clipboard';
import { notifyError } from '@/lib/notify-error';

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
      await copyText(code);
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
        <span className="font-mono text-white/60">{language ?? 'texto'}</span>
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
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed">{children}</pre>
    </div>
  );
}
