export interface DevCredentials {
  username: string;
  password: string;
}

/**
 * Throwaway local credentials for the quick-login card (see devLoginDefine in vite.config.ts).
 * null in builds, in tests and when the dev server is exposed with --host.
 */
export const DEV_LOGIN: DevCredentials | null = __DEV_LOGIN__;
