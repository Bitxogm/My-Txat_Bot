import { vi } from 'vitest';

export function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

export function streamResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(stream, { status, headers: { 'Content-Type': 'text/event-stream' } });
}

export function mockFetch(...responses: (Response | Error | DOMException)[]) {
  const fn = vi.fn<typeof globalThis.fetch>();
  for (const r of responses) {
    if (r instanceof Response) fn.mockResolvedValueOnce(r);
    else fn.mockRejectedValueOnce(r);
  }
  vi.stubGlobal('fetch', fn);
  return fn;
}
