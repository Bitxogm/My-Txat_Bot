import type { VitePWAOptions } from 'vite-plugin-pwa';

/** Colors of the icon background; the browser UI uses them while the app opens. */
export const PWA_BACKGROUND = '#0a0a0a';

/**
 * vite-plugin-pwa options (imported by vite.config.ts and checked by pwa/options.test.ts).
 *
 * The service worker only precaches the static shell. /api is NEVER handled by it: no
 * runtimeCaching route at all (not even NetworkOnly, which would still proxy SSE streams and
 * uploads through the worker) and excluded from the navigation fallback. Conversations,
 * attachments, thumbnails and the session always come from the network.
 */
export const pwaOptions: Partial<VitePWAOptions> = {
  // An update waits for the user ("Nueva versión disponible · Recargar"), never reloads by itself.
  registerType: 'prompt',
  // Registered from React (virtual:pwa-register/react): the inline script mode is blocked by
  // the CSP (script-src 'self').
  injectRegister: false,
  manifest: {
    name: 'Txat_bot',
    short_name: 'Txat',
    description: 'Chatbot personal para labs y CTF autorizados',
    lang: 'es',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    background_color: PWA_BACKGROUND,
    theme_color: PWA_BACKGROUND,
    icons: [
      { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
      { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
      { src: 'maskable-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
  },
  workbox: {
    globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
    navigateFallback: '/index.html',
    navigateFallbackDenylist: [/^\/api\//],
    runtimeCaching: [],
    cleanupOutdatedCaches: true,
  },
  devOptions: { enabled: false },
};
