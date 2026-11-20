import { useCallback, useEffect, useRef, useState } from 'react';
import { isAbortError, streamChat, type ChatMessage } from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export type MessageStatus = 'done' | 'streaming' | 'stopped' | 'error';

export interface UiMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  status: MessageStatus;
}

export interface UseChat {
  messages: UiMessage[];
  isStreaming: boolean;
  send: (content: string, model: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

function toHistory(messages: UiMessage[]): ChatMessage[] {
  // Failed or empty turns are not sent back to the model.
  return messages
    .filter((m) => m.status !== 'error' && m.content.trim() !== '')
    .map(({ role, content }) => ({ role, content }));
}

export function useChat(): UseChat {
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  // crypto.randomUUID needs a secure context, which plain-HTTP LAN access is not.
  const nextId = useRef(0);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const updateMessage = useCallback((id: number, update: (m: UiMessage) => UiMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? update(m) : m)));
  }, []);

  const send = useCallback(
    async (content: string, model: string) => {
      const text = content.trim();
      if (!text || controllerRef.current) return;

      const user: UiMessage = { id: nextId.current++, role: 'user', content: text, status: 'done' };
      const assistantId = nextId.current++;
      const history = [...toHistory(messages), { role: 'user' as const, content: text }];

      setMessages((prev) => [
        ...prev,
        user,
        { id: assistantId, role: 'assistant', content: '', status: 'streaming' },
      ]);
      const controller = new AbortController();
      controllerRef.current = controller;
      setIsStreaming(true);

      try {
        await streamChat(
          { model, messages: history },
          {
            signal: controller.signal,
            onToken: (token) =>
              updateMessage(assistantId, (m) => ({ ...m, content: m.content + token })),
          },
        );
        updateMessage(assistantId, (m) => ({ ...m, status: 'done' }));
      } catch (error) {
        if (isAbortError(error)) {
          updateMessage(assistantId, (m) => ({ ...m, status: 'stopped' }));
        } else {
          notifyError(error);
          updateMessage(assistantId, (m) => ({ ...m, status: 'error' }));
        }
      } finally {
        controllerRef.current = null;
        setIsStreaming(false);
      }
    },
    [messages, updateMessage],
  );

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, isStreaming, send, stop, reset };
}
