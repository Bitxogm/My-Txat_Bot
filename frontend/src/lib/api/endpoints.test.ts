import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  countConversationFeedback,
  listFeedback,
  rateMessage,
  unrateMessage,
  deleteAttachment,
  deleteConversation,
  renameConversation,
  sendMessage,
  streamChat,
  uploadAttachment,
} from './endpoints';
import { ApiError } from './errors';
import { jsonResponse, mockFetch, streamResponse } from './test-utils';

afterEach(() => {
  vi.unstubAllGlobals();
});

const body = { model: 'm', messages: [{ role: 'user' as const, content: 'hola' }] };

describe('streamChat', () => {
  it('streams tokens and resolves with the full reply', async () => {
    const fetchMock = mockFetch(
      streamResponse([
        'event: token\ndata: {"content": "Ho"}\n\n',
        'event: token\ndata: {"content": "la"}\n\n',
        'event: done\ndata: {"model": "m"}\n\n',
      ]),
    );
    const onToken = vi.fn();

    await expect(streamChat(body, { onToken })).resolves.toEqual({
      model: 'm',
      content: 'Hola',
      messageId: null,
    });
    expect(onToken.mock.calls).toEqual([['Ho'], ['la']]);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Accept')).toBe('text/event-stream');
  });

  it('throws the JSON error returned before the stream starts', async () => {
    mockFetch(
      jsonResponse(404, {
        error: { code: 'MODEL_NOT_FOUND', message: 'No existe', request_id: 'r1' },
      }),
    );

    await expect(streamChat(body, { onToken: vi.fn() })).rejects.toMatchObject({
      kind: 'not_found',
      code: 'MODEL_NOT_FOUND',
      requestId: 'r1',
    });
  });

  it('throws an ApiError for an error event mid-stream', async () => {
    mockFetch(
      streamResponse([
        'event: token\ndata: {"content": "a"}\n\n',
        'event: error\ndata: {"code": "MODEL_UNAVAILABLE", "message": "Caído", "request_id": "r2"}\n\n',
      ]),
    );

    const promise = streamChat(body, { onToken: vi.fn() });

    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({
      kind: 'server',
      code: 'MODEL_UNAVAILABLE',
      message: 'Caído',
      requestId: 'r2',
    });
  });

  it('treats a stream that ends without done as a network error', async () => {
    mockFetch(streamResponse(['event: token\ndata: {"content": "a"}\n\n']));

    await expect(streamChat(body, { onToken: vi.fn() })).rejects.toMatchObject({
      kind: 'network',
    });
  });
});

describe('conversation endpoints', () => {
  it('sendMessage streams from the conversation messages endpoint', async () => {
    const fetchMock = mockFetch(
      streamResponse([
        'event: token\ndata: {"content": "ok"}\n\n',
        'event: done\ndata: {"model": "m", "message_id": 42}\n\n',
      ]),
    );

    await expect(
      sendMessage('abc', { content: 'hola', model: 'm' }, { onToken: vi.fn() }),
    ).resolves.toEqual({ model: 'm', content: 'ok', messageId: 42 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/conversations/abc/messages');
    expect(init?.body).toBe('{"content":"hola","model":"m"}');
  });

  it('encodes ids and uses the right methods', async () => {
    const fetchMock = mockFetch(
      new Response(null, { status: 204 }),
      jsonResponse(200, { id: 'x', title: 'T', model: 'm', created_at: '', updated_at: '' }),
    );

    await deleteConversation('a/b');
    await renameConversation('x', 'T');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/conversations/a%2Fb');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('PATCH');
    expect(fetchMock.mock.calls[1][1]?.body).toBe('{"title":"T"}');
  });
});

describe('attachment endpoints', () => {
  it('uploads the file as multipart without forcing a Content-Type', async () => {
    const fetchMock = mockFetch(jsonResponse(201, { id: 'a' }));
    const file = new File(['hola'], 'notas.txt', { type: 'text/plain' });

    await uploadAttachment('c/1', file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/conversations/c%2F1/attachments');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get('file')).toBeInstanceOf(File);
    // The browser adds multipart/form-data with its boundary.
    expect(new Headers(init?.headers).get('Content-Type')).toBeNull();
  });

  it('deletes a pending attachment', async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await deleteAttachment('c1', 'a1');

    expect(fetchMock.mock.calls[0][0]).toBe('/api/conversations/c1/attachments/a1');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
  });
});

describe('stream errors', () => {
  it('carries the rate-limit fields of an error event', async () => {
    mockFetch(
      streamResponse([
        'event: error\ndata: {"code": "MODEL_RATE_LIMITED", "message": "m", "request_id": "r",' +
          ' "provider": "groq", "retry_after": 30}\n\n',
      ]),
    );

    await expect(streamChat(body, { onToken: vi.fn() })).rejects.toMatchObject({
      code: 'MODEL_RATE_LIMITED',
      provider: 'groq',
      retryAfter: 30,
    });
  });
});

describe('feedback endpoints', () => {
  it('rates and unrates a reply', async () => {
    const fetchMock = mockFetch(
      jsonResponse(200, { rating: -1, reasons: ['incorrect'], correction: 'x' }),
      new Response(null, { status: 204 }),
    );

    await rateMessage(7, { rating: -1, reasons: ['incorrect'], correction: 'x' });
    await unrateMessage(7);

    expect(fetchMock.mock.calls[0][0]).toBe('/api/messages/7/feedback');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('PUT');
    expect(fetchMock.mock.calls[0][1]?.body).toBe(
      '{"rating":-1,"reasons":["incorrect"],"correction":"x"}',
    );
    expect(fetchMock.mock.calls[1][0]).toBe('/api/messages/7/feedback');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('DELETE');
  });

  it('sends only the filters that are set', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { items: [], total: 0 }));

    await listFeedback({ rating: -1, model: undefined, reason: 'too_long' }, { limit: 20 });

    expect(fetchMock.mock.calls[0][0]).toBe('/api/feedback?rating=-1&reason=too_long&limit=20');
  });

  it('counts the ratings of a conversation', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { items: [], total: 3 }));

    await expect(countConversationFeedback('abc')).resolves.toBe(3);
    expect(fetchMock.mock.calls[0][0]).toBe('/api/feedback?conversation_id=abc&limit=1');
  });
});
