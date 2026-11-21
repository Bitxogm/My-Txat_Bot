import { afterEach, describe, expect, it, vi } from 'vitest';
import { clearRuntimeCaches } from './caches';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('clearRuntimeCaches', () => {
  it('deletes every cache except the precached shell', async () => {
    const storage = {
      keys: vi.fn(async () => ['workbox-precache-v2-http://x/', 'thumbnails', 'old-api']),
      delete: vi.fn(async (name: string) => name.length > 0),
    };
    vi.stubGlobal('caches', storage);

    await clearRuntimeCaches();

    expect(storage.delete.mock.calls.map(([name]) => name)).toEqual(['thumbnails', 'old-api']);
  });

  it('does nothing and never throws without Cache Storage', async () => {
    vi.stubGlobal('caches', {
      keys: vi.fn(async () => {
        throw new Error('SecurityError');
      }),
    });

    await expect(clearRuntimeCaches()).resolves.toBeUndefined();
  });
});
