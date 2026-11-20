import { CloudIcon } from 'lucide-react';
import type { ModelInfo, Personality } from '@/lib/api';
import { cn } from '@/lib/utils';
import { PersonalityIcon } from './personality-icon';

interface PersonalityPickerProps {
  personalities: Personality[];
  value: string;
  onChange: (personality: Personality) => void;
  models: ModelInfo[];
  disabled?: boolean;
}

/** Choose the personality of a new conversation. It can't change once the chat starts. */
export function PersonalityPicker({
  personalities,
  value,
  onChange,
  models,
  disabled,
}: PersonalityPickerProps) {
  const selected = personalities.find((p) => p.id === value);
  const remoteDefault =
    selected?.default_model != null &&
    models.some((m) => m.name === selected.default_model && m.remote);

  return (
    <section aria-labelledby="personality-picker-title" className="flex flex-col gap-3">
      <div>
        <h2 id="personality-picker-title" className="font-heading text-sm font-semibold">
          Elige una personalidad
        </h2>
        <p className="text-muted-foreground text-xs">
          Se fija al enviar el primer mensaje y no cambia durante la conversación.
        </p>
      </div>
      <div
        role="radiogroup"
        aria-labelledby="personality-picker-title"
        className="grid gap-2 sm:grid-cols-2"
      >
        {personalities.map((personality) => {
          const checked = personality.id === value;
          return (
            <button
              key={personality.id}
              type="button"
              role="radio"
              aria-checked={checked}
              aria-label={personality.name}
              aria-describedby={`personality-desc-${personality.id}`}
              disabled={disabled}
              onClick={() => onChange(personality)}
              className={cn(
                'hover:bg-muted flex items-start gap-3 rounded-lg border p-3 text-left transition-colors',
                checked && 'border-primary bg-muted ring-primary/30 ring-2',
              )}
            >
              <PersonalityIcon name={personality.icon} className="mt-0.5 size-4 shrink-0" />
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm font-medium">{personality.name}</span>
                <span
                  id={`personality-desc-${personality.id}`}
                  className="text-muted-foreground line-clamp-2 text-xs"
                >
                  {personality.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {remoteDefault && (
        <p className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300">
          <CloudIcon className="size-3.5 shrink-0" />
          Esta personalidad usa por defecto un modelo en la nube: lo que escribas saldrá de tu red.
        </p>
      )}
    </section>
  );
}
