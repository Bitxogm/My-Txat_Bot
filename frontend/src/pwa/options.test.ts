import { describe, expect, it } from 'vitest';
import { pwaOptions } from './options';

const API_PATHS = [
  '/api/auth/me',
  '/api/conversations/abc',
  '/api/conversations/abc/attachments/def/content',
];

describe('service worker options', () => {
  it('never handles /api: no runtime route and no navigation fallback for it', () => {
    const workbox = pwaOptions.workbox ?? {};

    expect(workbox.runtimeCaching ?? []).toEqual([]);
    for (const path of API_PATHS) {
      expect(workbox.navigateFallbackDenylist?.some((rule) => rule.test(path))).toBe(true);
    }
    expect(workbox.navigateFallbackDenylist?.some((rule) => rule.test('/'))).toBe(false);
  });

  it('precaches only static shell files', () => {
    const patterns = pwaOptions.workbox?.globPatterns ?? [];

    expect(patterns.join(' ')).not.toMatch(/json|api/);
  });

  it('asks before updating and registers without inline scripts (CSP)', () => {
    expect(pwaOptions.registerType).toBe('prompt');
    expect(pwaOptions.injectRegister).toBe(false);
  });

  it('is installable: standalone with regular and maskable icons', () => {
    const manifest = pwaOptions.manifest;
    if (!manifest) throw new Error('missing manifest');

    expect(manifest.display).toBe('standalone');
    expect(manifest.icons?.map((icon) => icon.sizes)).toEqual(
      expect.arrayContaining(['192x192', '512x512']),
    );
    expect(manifest.icons?.some((icon) => icon.purpose === 'maskable')).toBe(true);
  });
});
