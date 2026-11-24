import { useId, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { FeedbackReason, MessageFeedback } from '@/lib/api';
import { MAX_CORRECTION_CHARS, REASON_LABELS, REASONS } from './reasons';

export interface FeedbackFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The saved 👎, to edit it; null for a new one. */
  initial: MessageFeedback | null;
  /** Resolves true when saved (the dialog then closes). */
  onSubmit: (feedback: MessageFeedback) => Promise<boolean>;
  /** Shown when editing: removes the rating altogether. */
  onRemove?: () => Promise<boolean>;
}

/** The 👎 form: reasons and the right answer, all optional. Mounted only while open. */
export function FeedbackForm({ open, onOpenChange, ...rest }: FeedbackFormProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <FeedbackFormContent onOpenChange={onOpenChange} {...rest} />}
    </Dialog>
  );
}

function FeedbackFormContent({
  onOpenChange,
  initial,
  onSubmit,
  onRemove,
}: Omit<FeedbackFormProps, 'open'>) {
  const id = useId();
  const [reasons, setReasons] = useState<FeedbackReason[]>(initial?.reasons ?? []);
  const [correction, setCorrection] = useState(initial?.correction ?? '');
  const [busy, setBusy] = useState(false);

  function toggle(reason: FeedbackReason, checked: boolean) {
    setReasons((prev) =>
      checked
        ? REASONS.filter((r) => r === reason || prev.includes(r))
        : prev.filter((r) => r !== reason),
    );
  }

  async function run(action: () => Promise<boolean>) {
    setBusy(true);
    const ok = await action();
    setBusy(false);
    if (ok) onOpenChange(false);
  }

  return (
    <DialogContent className="sm:max-w-lg">
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void run(() =>
            onSubmit({ rating: -1, reasons, correction: correction.trim() ? correction : null }),
          );
        }}
      >
        <DialogHeader>
          <DialogTitle>¿Qué falla en esta respuesta?</DialogTitle>
          <DialogDescription>
            Todo es opcional. Se guarda para mejorar las respuestas más adelante; el modelo no lo ve
            todavía.
          </DialogDescription>
        </DialogHeader>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">Motivo</legend>
          {REASONS.map((reason) => (
            <div key={reason} className="flex items-center gap-2">
              <Checkbox
                id={`${id}-${reason}`}
                checked={reasons.includes(reason)}
                onCheckedChange={(v) => toggle(reason, v === true)}
              />
              <Label htmlFor={`${id}-${reason}`} className="font-normal">
                {REASON_LABELS[reason]}
              </Label>
            </div>
          ))}
        </fieldset>
        <div className="grid gap-2">
          <Label htmlFor={`${id}-correction`}>¿Cuál sería la respuesta correcta?</Label>
          <Textarea
            id={`${id}-correction`}
            value={correction}
            maxLength={MAX_CORRECTION_CHARS}
            rows={6}
            aria-describedby={`${id}-count`}
            onChange={(e) => setCorrection(e.target.value)}
          />
          <p id={`${id}-count`} className="text-muted-foreground text-right text-xs">
            {correction.length} / {MAX_CORRECTION_CHARS}
          </p>
        </div>
        <DialogFooter>
          {onRemove && (
            <Button
              type="button"
              variant="ghost"
              className="sm:mr-auto"
              disabled={busy}
              onClick={() => void run(onRemove)}
            >
              Quitar valoración
            </Button>
          )}
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" disabled={busy}>
            Guardar
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
