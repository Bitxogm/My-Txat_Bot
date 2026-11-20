import { useCallback, useEffect, useState } from 'react';
import { deleteConversation, isAbortError, listConversations, type Conversation } from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export interface UseConversations {
  conversations: Conversation[];
  loading: boolean;
  refresh: () => void;
  remove: (id: string) => Promise<boolean>;
}

export function useConversations(): UseConversations {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listConversations(controller.signal).then(
      (response) => {
        setConversations(response.conversations);
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

  const remove = useCallback(async (id: string) => {
    try {
      await deleteConversation(id);
    } catch (error) {
      notifyError(error);
      return false;
    }
    setConversations((prev) => prev.filter((c) => c.id !== id));
    return true;
  }, []);

  return { conversations, loading, refresh, remove };
}
