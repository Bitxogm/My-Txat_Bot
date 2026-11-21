import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createConversation,
  getConversation,
  isAbortError,
  sendMessage,
  type MessageAttachment,
  type Conversation,
  type PersonalityRef,
  type MessageStatus as StoredStatus,
  type StoredMessage,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export type MessageStatus = StoredStatus | 'streaming';

export interface UiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  status: MessageStatus;
  /** Files sent with a user message. */
  attachments: MessageAttachment[];
}

export interface UseChatOptions {
  /** Called after a conversation is created or receives a new turn (to refresh the sidebar). */
  onActivity?: () => void;
}

export interface UseChat {
  conversationId: string | null;
  /** Personality of the open conversation (fixed when it was created); null for a new chat. */
  personality: PersonalityRef | null;
  messages: UiMessage[];
  isStreaming: boolean;
  isLoading: boolean;
  open: (id: string) => Promise<Conversation | null>;
  startNew: () => void;
  /**
   * Id of the open conversation, creating it first if this is a new chat (files are uploaded to
   * a conversation). null if creating it failed (already notified).
   */
  ensureConversation: (model: string, personalityId?: string) => Promise<string | null>;
  /**
   * `personalityId` only matters for the first message, which creates the conversation.
   * Resolves with the conversation id (null if it couldn't be created or nothing was sent).
   */
  send: (
    content: string,
    model: string,
    personalityId?: string,
    attachments?: MessageAttachment[],
  ) => Promise<string | null>;
  stop: () => void;
}

function fromStored(message: StoredMessage): UiMessage | null {
  if (message.role === 'system') return null;
  return {
    id: `s${message.id}`,
    role: message.role,
    content: message.content,
    status: message.status,
    attachments: message.attachments ?? [],
  };
}

export function useChat({ onActivity }: UseChatOptions = {}): UseChat {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [personality, setPersonality] = useState<PersonalityRef | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const streamRef = useRef<AbortController | null>(null);
  const loadRef = useRef<AbortController | null>(null);
  const conversationRef = useRef<string | null>(null);
  // crypto.randomUUID needs a secure context, which plain-HTTP LAN access is not.
  const nextId = useRef(0);
  const onActivityRef = useRef(onActivity);

  useEffect(() => {
    onActivityRef.current = onActivity;
  }, [onActivity]);

  useEffect(
    () => () => {
      streamRef.current?.abort();
      loadRef.current?.abort();
    },
    [],
  );

  const select = useCallback((id: string | null) => {
    conversationRef.current = id;
    setConversationId(id);
  }, []);

  const updateMessage = useCallback((id: string, update: (m: UiMessage) => UiMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? update(m) : m)));
  }, []);

  const stop = useCallback(() => streamRef.current?.abort(), []);

  const startNew = useCallback(() => {
    streamRef.current?.abort();
    loadRef.current?.abort();
    select(null);
    setPersonality(null);
    setMessages([]);
    setIsLoading(false);
  }, [select]);

  const open = useCallback(
    async (id: string) => {
      // Leaving a reply in progress stops it; the server saves it as "stopped".
      streamRef.current?.abort();
      loadRef.current?.abort();
      const controller = new AbortController();
      loadRef.current = controller;
      select(id);
      setPersonality(null);
      setMessages([]);
      setIsLoading(true);
      try {
        const detail = await getConversation(id, controller.signal);
        setPersonality(detail.personality);
        setMessages(detail.messages.map(fromStored).filter((m) => m !== null));
        return detail;
      } catch (error) {
        if (isAbortError(error)) return null;
        notifyError(error);
        select(null);
        return null;
      } finally {
        if (loadRef.current === controller) {
          loadRef.current = null;
          setIsLoading(false);
        }
      }
    },
    [select],
  );

  const createIfNeeded = useCallback(
    async (model: string, personalityId?: string) => {
      const current = conversationRef.current;
      if (current) return current;
      const created = await createConversation({ model, personality_id: personalityId });
      setPersonality(created.personality);
      select(created.id);
      onActivityRef.current?.();
      return created.id;
    },
    [select],
  );

  const ensureConversation = useCallback(
    async (model: string, personalityId?: string) => {
      try {
        return await createIfNeeded(model, personalityId);
      } catch (error) {
        notifyError(error);
        return null;
      }
    },
    [createIfNeeded],
  );

  const send = useCallback(
    async (
      content: string,
      model: string,
      personalityId?: string,
      attachments: MessageAttachment[] = [],
    ) => {
      const text = content.trim();
      if (!text || streamRef.current) return null;

      const controller = new AbortController();
      streamRef.current = controller;
      setIsStreaming(true);

      const userId = `l${nextId.current++}`;
      const assistantId = `l${nextId.current++}`;
      setMessages((prev) => [
        ...prev,
        { id: userId, role: 'user', content: text, status: 'done', attachments },
        { id: assistantId, role: 'assistant', content: '', status: 'streaming', attachments: [] },
      ]);

      let id: string | null = conversationRef.current;
      try {
        id = await createIfNeeded(model, personalityId);
        const body =
          attachments.length > 0
            ? { content: text, model, attachment_ids: attachments.map((a) => a.id) }
            : { content: text, model };
        await sendMessage(id, body, {
          signal: controller.signal,
          onToken: (token) =>
            updateMessage(assistantId, (m) => ({ ...m, content: m.content + token })),
        });
        updateMessage(assistantId, (m) => ({ ...m, status: 'done' }));
      } catch (error) {
        if (isAbortError(error)) {
          updateMessage(assistantId, (m) => ({ ...m, status: 'stopped' }));
        } else {
          notifyError(error);
          updateMessage(assistantId, (m) => ({ ...m, status: 'error' }));
        }
      } finally {
        if (streamRef.current === controller) streamRef.current = null;
        setIsStreaming(false);
        onActivityRef.current?.();
      }
      return id;
    },
    [createIfNeeded, updateMessage],
  );

  return {
    conversationId,
    personality,
    messages,
    isStreaming,
    isLoading,
    open,
    startNew,
    ensureConversation,
    send,
    stop,
  };
}
