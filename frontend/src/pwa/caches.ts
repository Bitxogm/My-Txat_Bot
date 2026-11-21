/** Workbox names the shell precache "workbox-precache-v2-<scope>". */
const PRECACHE_PREFIX = 'workbox-precache';

/**
 * Deletes every Cache Storage cache except the precached app shell. Nothing under /api is ever
 * cached (pwa/options.ts), so this is defense in depth: after a logout no data of the session
 * may survive in the browser's caches. Never throws.
 */
export async function clearRuntimeCaches(): Promise<void> {
  if (typeof window === 'undefined' || !('caches' in window)) return;
  try {
    const names = await window.caches.keys();
    await Promise.all(
      names.filter((name) => !name.startsWith(PRECACHE_PREFIX)).map((name) => caches.delete(name)),
    );
  } catch {
    // Cache Storage unavailable (insecure context, private mode): nothing to clear.
  }
}
