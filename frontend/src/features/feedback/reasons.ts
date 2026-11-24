import type { FeedbackReason } from '@/lib/api';

/** Labels of the 👎 reasons; the API uses the stable codes (ADR-024). */
export const REASON_LABELS: Record<FeedbackReason, string> = {
  incorrect: 'Inventado o incorrecto',
  wrong_command: 'Comando o flag erróneo',
  incomplete: 'Incompleto',
  too_long: 'Demasiado largo',
  off_personality: 'No sigue la personalidad',
  other: 'Otro',
};

export const REASONS = Object.keys(REASON_LABELS) as FeedbackReason[];

export const MAX_CORRECTION_CHARS = 4000;
