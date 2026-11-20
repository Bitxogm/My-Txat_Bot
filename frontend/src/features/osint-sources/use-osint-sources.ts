import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  createOsintSource,
  deleteOsintSource,
  isAbortError,
  listOsintSources,
  replaceOsintSource,
  toggleOsintSource,
  type OsintSource,
  type OsintSourceInput,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export type SaveResult = { ok: true; source: OsintSource } | { ok: false; message: string | null };

export interface UseOsintSources {
  sources: OsintSource[];
  loading: boolean;
  toggle: (id: string) => Promise<void>;
  /** Validation errors come back as a message for the form; other errors go to a toast. */
  save: (input: OsintSourceInput, id?: string) => Promise<SaveResult>;
  remove: (id: string) => Promise<boolean>;
}

export function useOsintSources(): UseOsintSources {
  const [sources, setSources] = useState<OsintSource[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    listOsintSources(undefined, controller.signal).then(
      (response) => {
        setSources(response.sources);
        setLoading(false);
      },
      (error: unknown) => {
        if (isAbortError(error)) return;
        notifyError(error);
        setLoading(false);
      },
    );
    return () => controller.abort();
  }, []);

  const replaceInList = useCallback((updated: OsintSource) => {
    setSources((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
  }, []);

  const toggle = useCallback(
    async (id: string) => {
      try {
        replaceInList(await toggleOsintSource(id));
      } catch (error) {
        notifyError(error);
      }
    },
    [replaceInList],
  );

  const save = useCallback(
    async (input: OsintSourceInput, id?: string): Promise<SaveResult> => {
      try {
        if (id) {
          const updated = await replaceOsintSource(id, input);
          replaceInList(updated);
          return { ok: true, source: updated };
        }
        const created = await createOsintSource(input);
        setSources((prev) => [...prev, created]);
        return { ok: true, source: created };
      } catch (error) {
        if (error instanceof ApiError && (error.kind === 'validation' || error.status === 409)) {
          return { ok: false, message: error.message };
        }
        notifyError(error);
        return { ok: false, message: null };
      }
    },
    [replaceInList],
  );

  const remove = useCallback(async (id: string) => {
    try {
      await deleteOsintSource(id);
    } catch (error) {
      notifyError(error);
      return false;
    }
    setSources((prev) => prev.filter((s) => s.id !== id));
    return true;
  }, []);

  return { sources, loading, toggle, save, remove };
}
