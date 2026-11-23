import { LockIcon } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import type { Personality, PersonalityRef } from '@/lib/api';
import { PersonalityIcon } from './personality-icon';

export const LOCKED_HINT = 'La personalidad se fija al empezar la conversación';

interface PersonalitySelectProps {
  personalities: Personality[];
  value: string;
  onChange: (personality: Personality) => void;
  /** The conversation already started: show `fixed` and don't let it change (ADR-013). */
  locked: boolean;
  fixed: PersonalityRef | null;
  disabled?: boolean;
}

/** Compact personality chooser next to the model: free until the first message, then fixed. */
export function PersonalitySelect({
  personalities,
  value,
  onChange,
  locked,
  fixed,
  disabled,
}: PersonalitySelectProps) {
  if (locked) {
    const name = fixed?.name ?? 'Sin personalidad';
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {/* A focusable span: a disabled control gets no pointer or focus events. */}
            <span
              tabIndex={0}
              aria-label={`Personalidad: ${name}. ${LOCKED_HINT}`}
              className="text-muted-foreground flex h-8 max-w-44 items-center gap-1.5 rounded-md border px-2 text-sm"
            >
              <PersonalityIcon name={fixed?.icon} className="size-4 shrink-0" />
              <span className="truncate">{name}</span>
              <LockIcon className="size-3 shrink-0" aria-hidden="true" />
            </span>
          </TooltipTrigger>
          <TooltipContent>{LOCKED_HINT}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  const selected = personalities.find((p) => p.id === value);
  return (
    <Select
      value={selected ? value : undefined}
      onValueChange={(id) => {
        const personality = personalities.find((p) => p.id === id);
        if (personality) onChange(personality);
      }}
      disabled={disabled || personalities.length === 0}
    >
      <SelectTrigger size="sm" className="max-w-44" aria-label="Personalidad">
        <SelectValue placeholder="Personalidad">
          {selected && (
            <span className="flex min-w-0 items-center gap-1.5">
              <PersonalityIcon name={selected.icon} className="size-4 shrink-0" />
              <span className="truncate">{selected.name}</span>
            </span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="max-w-80">
        {personalities.map((p) => (
          <SelectItem key={p.id} value={p.id} aria-label={p.name}>
            <span className="flex items-start gap-2">
              <PersonalityIcon name={p.icon} className="mt-0.5 size-4 shrink-0" />
              <span className="flex min-w-0 flex-col">
                <span className="text-sm">{p.name}</span>
                <span className="text-muted-foreground line-clamp-2 text-xs">{p.description}</span>
              </span>
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
