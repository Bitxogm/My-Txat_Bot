import type { ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import type { Personality } from '@/lib/api';
import { PersonalityIcon } from './personality-icon';

interface PersonalityCardsProps {
  personalities: Personality[];
  /** Extra line under the description (e.g. the generation parameters). */
  details?: (personality: Personality) => ReactNode;
  /** Buttons of each card (view/edit, duplicate, delete). */
  actions: (personality: Personality) => ReactNode;
}

/**
 * The personalities as a grid of cards (it used to be the picker of a new chat; choosing now
 * happens in the chat header, so the cards live in the management page).
 */
export function PersonalityCards({ personalities, details, actions }: PersonalityCardsProps) {
  return (
    <ul className="grid gap-2 sm:grid-cols-2" aria-label="Lista de personalidades">
      {personalities.map((p) => (
        <li
          key={p.id}
          aria-label={p.name}
          className="flex flex-col justify-between gap-2 rounded-lg border p-3"
        >
          <div className="flex min-w-0 items-start gap-3">
            <PersonalityIcon name={p.icon} className="mt-0.5 size-4 shrink-0" />
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{p.name}</span>
                <Badge variant={p.builtin ? 'secondary' : 'outline'}>
                  {p.builtin ? 'Incorporada' : 'Propia'}
                </Badge>
              </div>
              <p className="text-muted-foreground text-xs">{p.description}</p>
              {details?.(p)}
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-1">{actions(p)}</div>
        </li>
      ))}
    </ul>
  );
}
