import type { OsintCategory } from '@/lib/api';

/** Same order as the backend (domain/osint.py). */
export const OSINT_CATEGORIES: { value: OsintCategory; label: string }[] = [
  { value: 'breach', label: 'Filtraciones' },
  { value: 'username', label: 'Usuarios' },
  { value: 'domain', label: 'Dominios' },
  { value: 'image', label: 'Imágenes' },
  { value: 'code', label: 'Código' },
  { value: 'forum', label: 'Foros' },
  { value: 'browser_fingerprint', label: 'Navegador' },
  { value: 'aggregator', label: 'Agregadores' },
];

export function categoryLabel(category: OsintCategory): string {
  return OSINT_CATEGORIES.find((c) => c.value === category)?.label ?? category;
}
