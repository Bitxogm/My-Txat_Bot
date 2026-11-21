import { afterEach, describe, expect, it, vi } from 'vitest';
import { request, setUnauthorizedHandler } from './client';
import { ApiError } from './errors';
import { jsonResponse, mockFetch } from './test-utils';

afterEach(() => {
  vi.unstubAllGlobals();
});

async function catchError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error;
    throw error;
  }
  throw new Error('expected the request to fail');
}

describe('request', () => {
  it('returns parsed JSON and sends to /api with same-origin credentials', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { status: 'ok' }));

    await expect(request('/health')).resolves.toEqual({ status: 'ok' });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/health');
    expect(init?.credentials).toBe('same-origin');
  });

  it('serializes JSON bodies', async () => {
    const fetchMock = mockFetch(jsonResponse(200, {}));

    await request('/x', { method: 'POST', body: { a: 1 } });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.body).toBe('{"a":1}');
    expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
  });

  it.each([
    [400, 'validation'],
    [422, 'validation'],
    [401, 'unauthorized'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [413, 'payload_too_large'],
    [415, 'unsupported_media_type'],
    [411, 'validation'],
    [429, 'rate_limited'],
    [500, 'server'],
    [503, 'server'],
  ] as const)('maps HTTP %i to %s', async (status, kind) => {
    mockFetch(
      jsonResponse(status, { error: { code: 'SOME_CODE', message: 'msg', request_id: 'rid' } }),
    );

    const error = await catchError(request('/x'));

    expect(error.kind).toBe(kind);
    expect(error.status).toBe(status);
    expect(error.code).toBe('SOME_CODE');
    expect(error.message).toBe('msg');
    expect(error.requestId).toBe('rid');
  });

  it('falls back to a generic message and the header request id for non-JSON errors', async () => {
    mockFetch(
      new Response('<html>Bad Gateway</html>', { status: 502, headers: { 'X-Request-ID': 'h1' } }),
    );

    const error = await catchError(request('/x'));

    expect(error.kind).toBe('server');
    expect(error.code).toBe('HTTP_502');
    expect(error.requestId).toBe('h1');
    expect(error.message).not.toContain('html');
  });

  it('maps network failures to a network error', async () => {
    mockFetch(new TypeError('Failed to fetch'));

    const error = await catchError(request('/x'));

    expect(error.kind).toBe('network');
    expect(error.status).toBeNull();
  });

  it('rethrows aborts untouched', async () => {
    mockFetch(new DOMException('aborted', 'AbortError'));

    await expect(request('/x')).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('calls the unauthorized handler on 401', async () => {
    const handler = vi.fn();
    const unsubscribe = setUnauthorizedHandler(handler);
    mockFetch(
      jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'no', request_id: 'r' } }),
    );

    await catchError(request('/x'));
    unsubscribe();

    expect(handler).toHaveBeenCalledOnce();
    expect(handler.mock.calls[0][0]).toBeInstanceOf(ApiError);
  });
});
