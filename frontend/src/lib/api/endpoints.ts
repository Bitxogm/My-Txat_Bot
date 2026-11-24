import { API_BASE, networkError, rateLimitFields, request, send } from './client';
import { ApiError, fallbackMessage, isAbortError } from './errors';
import { readSse } from './sse';
import type {
  Attachment,
  AttachmentList,
  ChatRequest,
  ChatResult,
  Conversation,
  ConversationDetail,
  ConversationList,
  Feedback,
  FeedbackFilters,
  FeedbackPage,
  MessageFeedback,
  HealthResponse,
  LoginRequest,
  MeResponse,
  ModelsResponse,
  OsintCategory,
  OsintSource,
  OsintSourceInput,
  OsintSourceList,
  Personality,
  PersonalityInput,
  PersonalityList,
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
        const messageId = typeof payload.message_id === 'number' ? payload.message_id : null;
        return { model: asString(payload.model) ?? fallbackModel, content, messageId };
      } else if (event === 'error') {
        throw new ApiError({
          kind: 'server',
          status: null,
          code: asString(payload.code) ?? 'STREAM_ERROR',
          message: asString(payload.message) ?? fallbackMessage('server'),
          requestId: asString(payload.request_id),
          ...rateLimitFields(payload),
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

export function createConversation(body: {
  model?: string;
  personality_id?: string;
}): Promise<Conversation> {
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

/** Change the personality of a draft (no message yet, ADR-022); 409 PERSONALITY_LOCKED after. */
export function setConversationPersonality(
  id: string,
  personalityId: string,
): Promise<Conversation> {
  return request<Conversation>(`/conversations/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { personality_id: personalityId },
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await send(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Persistent chat: the server stores the turn and builds the history. Same events as streamChat. */
export function sendMessage(
  id: string,
  body: { content: string; model?: string; attachment_ids?: string[] },
  options: StreamChatOptions,
): Promise<ChatResult> {
  return streamReply(
    `/conversations/${encodeURIComponent(id)}/messages`,
    body,
    body.model ?? '',
    options,
  );
}

function attachmentsPath(conversationId: string): string {
  return `/conversations/${encodeURIComponent(conversationId)}/attachments`;
}

/** Uploads one file to a conversation; it stays pending until a message sends it. */
export function uploadAttachment(
  conversationId: string,
  file: File,
  signal?: AbortSignal,
): Promise<Attachment> {
  const form = new FormData();
  form.append('file', file, file.name);
  return request<Attachment>(attachmentsPath(conversationId), {
    method: 'POST',
    body: form,
    signal,
  });
}

export function listAttachments(
  conversationId: string,
  signal?: AbortSignal,
): Promise<AttachmentList> {
  return request<AttachmentList>(attachmentsPath(conversationId), { signal });
}

/**
 * Address of an image attachment (re-encoded by the server) for an <img> or a link. Images only;
 * the browser sends the session cookie because it is same-origin.
 */
export function attachmentContentUrl(conversationId: string, id: string): string {
  return `${API_BASE}${attachmentsPath(conversationId)}/${encodeURIComponent(id)}/content`;
}

/** Removes a file not sent yet. */
export async function deleteAttachment(conversationId: string, id: string): Promise<void> {
  await send(`${attachmentsPath(conversationId)}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
}

export function listPersonalities(signal?: AbortSignal): Promise<PersonalityList> {
  return request<PersonalityList>('/personalities', { signal });
}

export function createPersonality(body: PersonalityInput): Promise<Personality> {
  return request<Personality>('/personalities', { method: 'POST', body });
}

export function updatePersonality(
  id: string,
  body: Partial<PersonalityInput>,
): Promise<Personality> {
  return request<Personality>(`/personalities/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body,
  });
}

export async function deletePersonality(id: string): Promise<void> {
  await send(`/personalities/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function duplicatePersonality(id: string): Promise<Personality> {
  return request<Personality>(`/personalities/${encodeURIComponent(id)}/duplicate`, {
    method: 'POST',
  });
}

export function listOsintSources(
  category?: OsintCategory,
  signal?: AbortSignal,
): Promise<OsintSourceList> {
  const query = category ? `?category=${encodeURIComponent(category)}` : '';
  return request<OsintSourceList>(`/osint-sources${query}`, { signal });
}

export function createOsintSource(body: OsintSourceInput): Promise<OsintSource> {
  return request<OsintSource>('/osint-sources', { method: 'POST', body });
}

/** Full replacement. On a built-in only `is_active` may differ from the stored values. */
export function replaceOsintSource(id: string, body: OsintSourceInput): Promise<OsintSource> {
  return request<OsintSource>(`/osint-sources/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body,
  });
}

export function toggleOsintSource(id: string): Promise<OsintSource> {
  return request<OsintSource>(`/osint-sources/${encodeURIComponent(id)}/toggle`, {
    method: 'POST',
  });
}

export async function deleteOsintSource(id: string): Promise<void> {
  await send(`/osint-sources/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Create or replace the rating of an assistant reply. */
export function rateMessage(messageId: number, body: MessageFeedback): Promise<Feedback> {
  return request<Feedback>(`/messages/${messageId}/feedback`, { method: 'PUT', body });
}

export async function unrateMessage(messageId: number): Promise<void> {
  await send(`/messages/${messageId}/feedback`, { method: 'DELETE' });
}

function feedbackQuery(filters: FeedbackFilters, extra: Record<string, number> = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...extra })) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

export function listFeedback(
  filters: FeedbackFilters = {},
  page: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<FeedbackPage> {
  return request<FeedbackPage>(`/feedback${feedbackQuery(filters, page)}`, { signal });
}

/** How many ratings a conversation has (they go with it when it is deleted). */
export async function countConversationFeedback(
  conversationId: string,
  signal?: AbortSignal,
): Promise<number> {
  const page = await listFeedback({ conversation_id: conversationId }, { limit: 1 }, signal);
  return page.total;
}

export interface FeedbackExport {
  blob: Blob;
  filename: string;
}

const EXPORT_FILENAME = /filename="([\w.-]+)"/;

/** The matching ratings as a JSONL file (docs/feedback-export.md), to hand to the browser. */
export async function exportFeedback(filters: FeedbackFilters = {}): Promise<FeedbackExport> {
  const response = await send(`/feedback/export${feedbackQuery(filters)}`, {
    accept: 'application/x-ndjson',
  });
  const match = EXPORT_FILENAME.exec(response.headers.get('Content-Disposition') ?? '');
  return { blob: await response.blob(), filename: match?.[1] ?? 'txat-feedback.jsonl' };
}
