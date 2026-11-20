import { networkError, request, send } from './client';
import { ApiError, fallbackMessage, isAbortError } from './errors';
import { readSse } from './sse';
import type {
  ChatRequest,
  ChatResult,
  Conversation,
  ConversationDetail,
  ConversationList,
  HealthResponse,
  LoginRequest,
  MeResponse,
  ModelsResponse,
} from './types';

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { signal });
}

export async function login(credentials: LoginRequest): Promise<void> {
  await send('/auth/login', { method: 'POST', body: credentials });
}

export async function logout(): Promise<void> {
  await send('/auth/logout', { method: 'POST' });
}

export function getMe(signal?: AbortSignal): Promise<MeResponse> {
  return request<MeResponse>('/auth/me', { signal });
}

export function listModels(signal?: AbortSignal): Promise<ModelsResponse> {
  return request<ModelsResponse>('/models', { signal });
}

export interface StreamChatOptions {
  onToken: (content: string) => void;
  signal?: AbortSignal;
}

function parseData(data: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(data);
    if (typeof parsed === 'object' && parsed !== null) return parsed as Record<string, unknown>;
  } catch {
    // handled below
  }
  return {};
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

async function streamReply(
  path: string,
  body: unknown,
  fallbackModel: string,
  { onToken, signal }: StreamChatOptions,
): Promise<ChatResult> {
  const response = await send(path, {
    method: 'POST',
    body,
    signal,
    accept: 'text/event-stream',
  });
  if (!response.body) throw networkError();

  let content = '';
  try {
    for await (const { event, data } of readSse(response.body)) {
      const payload = parseData(data);
      if (event === 'token') {
        const token = asString(payload.content) ?? '';
        content += token;
        onToken(token);
      } else if (event === 'done') {
        return { model: asString(payload.model) ?? fallbackModel, content };
      } else if (event === 'error') {
        throw new ApiError({
          kind: 'server',
          status: null,
          code: asString(payload.code) ?? 'STREAM_ERROR',
          message: asString(payload.message) ?? fallbackMessage('server'),
          requestId: asString(payload.request_id),
        });
      }
    }
  } catch (error) {
    if (error instanceof ApiError || isAbortError(error)) throw error;
    throw networkError();
  }
  // The stream ended without `done`: the connection was cut.
  throw networkError();
}

/**
 * Stateless chat: streams a reply to the whole history sent by the client. Calls onToken per
 * chunk and resolves with the full reply on `done`. Throws ApiError (HTTP error before the
 * stream, `error` event, or a cut connection) or the AbortError from `signal`.
 */
export function streamChat(body: ChatRequest, options: StreamChatOptions): Promise<ChatResult> {
  return streamReply('/chat', body, body.model ?? '', options);
}

export function listConversations(signal?: AbortSignal): Promise<ConversationList> {
  return request<ConversationList>('/conversations', { signal });
}

export function createConversation(body: { model?: string }): Promise<Conversation> {
  return request<Conversation>('/conversations', { method: 'POST', body });
}

export function getConversation(id: string, signal?: AbortSignal): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`, { signal });
}

export function renameConversation(id: string, title: string): Promise<Conversation> {
  return request<Conversation>(`/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { title },
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await send(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Persistent chat: the server stores the turn and builds the history. Same events as streamChat. */
export function sendMessage(
  id: string,
  body: { content: string; model?: string },
  options: StreamChatOptions,
): Promise<ChatResult> {
  return streamReply(
    `/conversations/${encodeURIComponent(id)}/messages`,
    body,
    body.model ?? '',
    options,
  );
}
