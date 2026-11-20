import { describe, expect, it } from 'vitest';
import { readSse, type SseEvent } from './sse';
import { streamResponse } from './test-utils';

async function collect(chunks: string[]): Promise<SseEvent[]> {
  const body = streamResponse(chunks).body;
  if (!body) throw new Error('no body');
  const events: SseEvent[] = [];
  for await (const event of readSse(body)) events.push(event);
  return events;
}

describe('readSse', () => {
  it('parses events split across arbitrary chunks', async () => {
    const events = await collect([
      'event: tok',
      'en\ndata: {"content":"Ho',
      'la"}\n\nevent: done\nda',
      'ta: {}\n\n',
    ]);

    expect(events).toEqual([
      { event: 'token', data: '{"content":"Hola"}' },
      { event: 'done', data: '{}' },
    ]);
  });

  it('handles CRLF, comments, multi-line data and a final event without blank line', async () => {
    const events = await collect([
      ': ping\r\n\r\n',
      'data: a\r\ndata: b\r\n\r\n',
      'event: x\ndata: 1',
    ]);

    expect(events).toEqual([
      { event: 'message', data: 'a\nb' },
      { event: 'x', data: '1' },
    ]);
  });
});
