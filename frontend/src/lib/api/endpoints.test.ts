import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamChat } from './endpoints';
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

    await expect(streamChat(body, { onToken })).resolves.toEqual({ model: 'm', content: 'Hola' });
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
