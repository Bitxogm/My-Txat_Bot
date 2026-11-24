import { ThumbsDownIcon, ThumbsUpIcon } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { MessageFeedback } from '@/lib/api';
import { cn } from '@/lib/utils';
import { FeedbackForm } from './feedback-form';

export interface FeedbackButtonsProps {
  feedback: MessageFeedback | null;
  /** Save a rating, or remove it with null. Resolves true when it worked. */
  onRate: (feedback: MessageFeedback | null) => Promise<boolean>;
  className?: string;
}

/**
 * 👍/👎 under a reply. 👍 again removes it; 👎 opens the form (to create or edit, with an
 * option to remove). Discreet until hovered or focused, always visible on touch screens and once
 * the reply is rated.
 */
export function FeedbackButtons({ feedback, onRate, className }: FeedbackButtonsProps) {
  const [formOpen, setFormOpen] = useState(false);
  const rating = feedback?.rating ?? null;

  return (
    <div
      role="group"
      aria-label="Valorar respuesta"
      className={cn(
        'flex items-center gap-0.5 transition-opacity',
        rating === null &&
          'opacity-0 group-hover:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100',
        className,
      )}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        aria-label="Respuesta útil"
        aria-pressed={rating === 1}
        title={rating === 1 ? 'Quitar valoración' : 'Respuesta útil'}
        className={cn(rating === 1 && 'text-primary')}
        onClick={() =>
          void onRate(rating === 1 ? null : { rating: 1, reasons: [], correction: null })
        }
      >
        <ThumbsUpIcon className={cn(rating === 1 && 'fill-current')} />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        aria-label="Respuesta mejorable"
        aria-pressed={rating === -1}
        aria-haspopup="dialog"
        title={rating === -1 ? 'Editar o quitar la valoración' : 'Respuesta mejorable'}
        className={cn(rating === -1 && 'text-destructive')}
        onClick={() => setFormOpen(true)}
      >
        <ThumbsDownIcon className={cn(rating === -1 && 'fill-current')} />
      </Button>
      <FeedbackForm
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={rating === -1 ? feedback : null}
        onSubmit={onRate}
        onRemove={rating === -1 ? () => onRate(null) : undefined}
      />
    </div>
  );
}
