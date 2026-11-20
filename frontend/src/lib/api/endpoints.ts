import { networkError, request, send } from './client';
import { ApiError, fallbackMessage, isAbortError } from './errors';
import { readSse } from './sse';
import type { ChatRequest, ChatResult, HealthResponse, ModelsResponse } from './types';

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { signal });
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

/**
 * Streams a chat reply. Calls onToken per chunk and resolves with the full reply on `done`.
 * Throws ApiError (HTTP error before the stream, `error` event, or a cut connection) or the
 * AbortError from `signal`.
 */
export async function streamChat(
  body: ChatRequest,
  { onToken, signal }: StreamChatOptions,
): Promise<ChatResult> {
  const response = await send('/chat', {
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
        return { model: asString(payload.model) ?? body.model ?? '', content };
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
