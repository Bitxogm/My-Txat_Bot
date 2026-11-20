import { useCallback, useEffect, useState } from 'react';
import {
  createPersonality,
  deletePersonality,
  duplicatePersonality,
  isAbortError,
  listPersonalities,
  updatePersonality,
  type Personality,
  type PersonalityInput,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export const DEFAULT_PERSONALITY_ID = 'builtin-mentor-ctf';

export interface UsePersonalities {
  personalities: Personality[];
  loading: boolean;
  refresh: () => void;
  /** Resolve with the saved personality, or null if it failed (the error is already shown). */
  save: (input: PersonalityInput, id?: string) => Promise<Personality | null>;
  duplicate: (id: string) => Promise<Personality | null>;
  remove: (id: string) => Promise<boolean>;
}

export function usePersonalities(): UsePersonalities {
  const [personalities, setPersonalities] = useState<Personality[]>([]);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listPersonalities(controller.signal).then(
      (response) => {
        setPersonalities(response.personalities);
        setLoading(false);
      },
      (error: unknown) => {
        if (isAbortError(error)) return;
        notifyError(error);
        setLoading(false);
      },
    );
    return () => controller.abort();
  }, [version]);

  const refresh = useCallback(() => setVersion((n) => n + 1), []);

  const save = useCallback(
    async (input: PersonalityInput, id?: string) => {
      try {
        const saved = id ? await updatePersonality(id, input) : await createPersonality(input);
        refresh();
        return saved;
      } catch (error) {
        notifyError(error);
        return null;
      }
    },
    [refresh],
  );

  const duplicate = useCallback(
    async (id: string) => {
      try {
        const copy = await duplicatePersonality(id);
        refresh();
        return copy;
      } catch (error) {
        notifyError(error);
        return null;
      }
    },
    [refresh],
  );

  const remove = useCallback(async (id: string) => {
    try {
      await deletePersonality(id);
    } catch (error) {
      notifyError(error);
      return false;
    }
    setPersonalities((prev) => prev.filter((p) => p.id !== id));
    return true;
  }, []);

  return { personalities, loading, refresh, save, duplicate, remove };
}
