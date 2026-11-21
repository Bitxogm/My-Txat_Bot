import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vitest/config';
import { pwaOptions } from './src/pwa/options.ts';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);

/**
 * Quick-login card values (written by `app.cli dev-login` to .env.local without the VITE_
 * prefix, so Vite never exposes them on its own). Injected only for `vite serve` on a local
 * host: never in builds or tests, and not with --host, where anyone on the network could read
 * the served module.
 */
function devLoginDefine(command: string, mode: string, env: Record<string, string>): string {
  const user = env.DEV_LOGIN_USER;
  const password = env.DEV_LOGIN_PASSWORD;
  if (command !== 'serve' || mode === 'test' || !user || !password) return 'null';
  const hostFlag = process.argv.findIndex((arg) => arg === '--host' || arg.startsWith('--host='));
  if (hostFlag !== -1) {
    const value = process.argv[hostFlag].split('=')[1] ?? process.argv[hostFlag + 1];
    if (!value || value.startsWith('-') || !LOCAL_HOSTS.has(value)) {
      console.warn(
        '[dev-login] Servidor expuesto con --host: tarjeta de acceso rápido desactivada.',
      );
      return 'null';
    }
  }
  return JSON.stringify({ username: user, password });
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // Dev only: /api goes to the local backend. In Docker, nginx does this proxying.
  const backendUrl = env.VITE_DEV_BACKEND_URL || 'http://localhost:8000';

  return {
    plugins: [react(), tailwindcss(), VitePWA(pwaOptions)],
    define: { __DEV_LOGIN__: devLoginDefine(command, mode, env) },
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, './src') },
    },
    server: {
      proxy: { '/api': { target: backendUrl, changeOrigin: false } },
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
