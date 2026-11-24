import { useCallback, useEffect, useRef, useState } from 'react';
import {
  exportFeedback,
  isAbortError,
  listFeedback,
  rateMessage,
  unrateMessage,
  type Feedback,
  type FeedbackFilters,
  type MessageFeedback,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export const PAGE_SIZE = 20;

export interface UseCorrections {
  items: Feedback[];
  total: number;
  loading: boolean;
  filters: FeedbackFilters;
  setFilters: (filters: FeedbackFilters) => void;
  loadMore: () => Promise<void>;
  /** Change a rating (null removes it). Resolves true when it worked. */
  rate: (messageId: number, feedback: MessageFeedback | null) => Promise<boolean>;
  /** Download the ratings matching the current filters as JSONL. */
  download: () => Promise<void>;
}

/** Hands a file to the browser as a download. */
function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function useCorrections(): UseCorrections {
  const [items, setItems] = useState<Feedback[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFiltersState] = useState<FeedbackFilters>({});
  const itemsRef = useRef(items);

  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  useEffect(() => {
    const controller = new AbortController();
    listFeedback(filters, { limit: PAGE_SIZE, offset: 0 }, controller.signal)
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) notifyError(error);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [filters]);

  const setFilters = useCallback((next: FeedbackFilters) => {
    setLoading(true);
    setFiltersState(next);
  }, []);

  const loadMore = useCallback(async () => {
    setLoading(true);
    try {
      const page = await listFeedback(filters, {
        limit: PAGE_SIZE,
        offset: itemsRef.current.length,
      });
      setItems((prev) => {
        const seen = new Set(prev.map((f) => f.message_id));
        return [...prev, ...page.items.filter((f) => !seen.has(f.message_id))];
      });
      setTotal(page.total);
    } catch (error) {
      notifyError(error);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const rate = useCallback(async (messageId: number, feedback: MessageFeedback | null) => {
    try {
      if (feedback) {
        const saved = await rateMessage(messageId, feedback);
        setItems((prev) => prev.map((f) => (f.message_id === messageId ? saved : f)));
      } else {
        await unrateMessage(messageId);
        setItems((prev) => prev.filter((f) => f.message_id !== messageId));
        setTotal((n) => Math.max(0, n - 1));
      }
      return true;
    } catch (error) {
      notifyError(error);
      return false;
    }
  }, []);

  const download = useCallback(async () => {
    try {
      const { blob, filename } = await exportFeedback(filters);
      saveFile(blob, filename);
    } catch (error) {
      notifyError(error);
    }
  }, [filters]);

  return { items, total, loading, filters, setFilters, loadMore, rate, download };
}
