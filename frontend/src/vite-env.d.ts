/// <reference types="vite/client" />

/** Dev-only quick-login credentials, injected by vite.config.ts (null outside `vite serve`). */
declare const __DEV_LOGIN__: { username: string; password: string } | null;
