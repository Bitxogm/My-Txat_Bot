import type { PersonalityRef } from '@/lib/api';
import { PersonalityIcon } from './personality-icon';

/** Read-only label with the personality a conversation was created with. */
export function PersonalityBadge({ personality }: { personality: PersonalityRef | null }) {
  return (
    <span
      className="text-muted-foreground flex min-w-0 items-center gap-1.5 text-sm"
      title="Personalidad fijada al crear esta conversación"
    >
      <PersonalityIcon name={personality?.icon} className="size-4 shrink-0" />
      <span className="truncate">{personality?.name ?? 'Sin personalidad'}</span>
    </span>
  );
}
