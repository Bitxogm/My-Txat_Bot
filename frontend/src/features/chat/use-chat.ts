import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  createConversation,
  getConversation,
  isAbortError,
  rateMessage,
  sendMessage,
  unrateMessage,
  type MessageAttachment,
  type MessageFeedback,
  type Conversation,
  type PersonalityRef,
  type MessageStatus as StoredStatus,
  type StoredMessage,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export type MessageStatus = StoredStatus | 'streaming';

export const RATE_LIMITED = 'MODEL_RATE_LIMITED';

export interface UiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  status: MessageStatus;
  /** Files sent with a user message. */
  attachments: MessageAttachment[];
  /** Id of the stored message, once the server has it (needed to rate a reply). */
  serverId?: number;
  /** Rating of an assistant reply (ADR-024). */
  feedback?: MessageFeedback | null;
}

/** Replies that can be rated: stored, finished or stopped, with text. */
export function canRate(message: UiMessage): boolean {
  return (
    message.role === 'assistant' &&
    message.serverId !== undefined &&
    (message.status === 'done' || message.status === 'stopped') &&
    message.content.trim() !== ''
  );
}

/**
 * The model failed before answering (HTTP error before the stream): the server did not keep the
 * turn (ADR-019), so it is taken off the screen and its text goes back to the composer.
 */
export interface FailedSend {
  text: string;
  error: ApiError;
}

export interface SendResult {
  /** The conversation, created by this send if it was a new chat (null if that failed). */
  conversationId: string | null;
  failed: FailedSend | null;
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
  /** The draft's personality changed on the server (ADR-022). */
  setPersonality: (personality: PersonalityRef | null) => void;
  /**
   * `personalityId` only matters for the first message, which creates the conversation.
   * Never rejects: a failure before the reply comes back in `failed` (already notified, except
   * a rate limit, which the page shows itself).
   */
  send: (
    content: string,
    model: string,
    personalityId?: string,
    attachments?: MessageAttachment[],
  ) => Promise<SendResult>;
  stop: () => void;
  /** Rate a reply (null removes the rating). Optimistic; reverted and notified on failure. */
  rate: (localId: string, feedback: MessageFeedback | null) => Promise<boolean>;
}

// A stopped reply is saved by the server after the connection closes: look for it a few times.
const STOPPED_REPLY_LOOKUPS = [0, 300, 1000];

function fromStored(message: StoredMessage): UiMessage | null {
  if (message.role === 'system') return null;
  return {
    id: `s${message.id}`,
    role: message.role,
    content: message.content,
    status: message.status,
    attachments: message.attachments ?? [],
    serverId: message.id,
    feedback: message.feedback ?? null,
  };
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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
  const messagesRef = useRef(messages);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

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

  /** The server id of a reply the user stopped (it isn't in any event), so it can be rated. */
  const findStoppedReply = useCallback(
    async (conversation: string, localId: string) => {
      for (const delay of STOPPED_REPLY_LOOKUPS) {
        if (delay) await wait(delay);
        if (conversationRef.current !== conversation) return;
        let detail;
        try {
          detail = await getConversation(conversation);
        } catch {
          return; // only costs the rating buttons on this reply until it is reopened
        }
        const last = detail.messages.at(-1);
        if (last?.role === 'assistant' && last.status === 'stopped') {
          updateMessage(localId, (m) => ({ ...m, serverId: last.id, feedback: null }));
          return;
        }
      }
    },
    [updateMessage],
  );

  const rate = useCallback(
    async (localId: string, feedback: MessageFeedback | null) => {
      const target = messagesRef.current.find((m) => m.id === localId);
      const serverId = target?.serverId;
      if (target === undefined || serverId === undefined) return false;
      const before = target.feedback ?? null;
      updateMessage(localId, (m) => ({ ...m, feedback }));
      try {
        if (feedback) {
          const saved = await rateMessage(serverId, feedback);
          updateMessage(localId, (m) => ({
            ...m,
            feedback: {
              rating: saved.rating,
              reasons: saved.reasons,
              correction: saved.correction,
            },
          }));
        } else {
          await unrateMessage(serverId);
        }
        return true;
      } catch (error) {
        updateMessage(localId, (m) => ({ ...m, feedback: before }));
        notifyError(error);
        return false;
      }
    },
    [updateMessage],
  );

  const send = useCallback(
    async (
      content: string,
      model: string,
      personalityId?: string,
      attachments: MessageAttachment[] = [],
    ) => {
      const text = content.trim();
      if (!text || streamRef.current)
        return { conversationId: conversationRef.current, failed: null };

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
      let received = false;
      let failed: FailedSend | null = null;
      try {
        id = await createIfNeeded(model, personalityId);
        const body =
          attachments.length > 0
            ? { content: text, model, attachment_ids: attachments.map((a) => a.id) }
            : { content: text, model };
        const result = await sendMessage(id, body, {
          signal: controller.signal,
          onToken: (token) => {
            received = true;
            updateMessage(assistantId, (m) => ({ ...m, content: m.content + token }));
          },
        });
        updateMessage(assistantId, (m) => ({
          ...m,
          status: 'done',
          serverId: result.messageId ?? undefined,
          feedback: null,
        }));
      } catch (error) {
        if (isAbortError(error)) {
          updateMessage(assistantId, (m) => ({ ...m, status: 'stopped' }));
          if (id && received) void findStoppedReply(id, assistantId);
        } else if (error instanceof ApiError && error.status !== null && !received) {
          // An HTTP error before the stream: nothing was stored, nothing stays on screen.
          setMessages((prev) => prev.filter((m) => m.id !== userId && m.id !== assistantId));
          if (error.code !== RATE_LIMITED) notifyError(error);
          failed = { text, error };
        } else {
          notifyError(error);
          updateMessage(assistantId, (m) => ({ ...m, status: 'error' }));
        }
      } finally {
        if (streamRef.current === controller) streamRef.current = null;
        setIsStreaming(false);
        onActivityRef.current?.();
      }
      return { conversationId: id, failed };
    },
    [createIfNeeded, findStoppedReply, updateMessage],
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
    setPersonality,
    send,
    stop,
    rate,
  };
}
