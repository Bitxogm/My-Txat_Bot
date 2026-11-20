export interface DevCredentials {
  username: string;
  password: string;
}

/**
 * Throwaway local credentials for the quick-login card. Only in `npm run dev`: in production
 * builds `import.meta.env.DEV` is false, so this folds to null and the values are not bundled.
 */
export const DEV_LOGIN: DevCredentials | null =
  import.meta.env.DEV &&
  import.meta.env.VITE_DEV_LOGIN_USER &&
  import.meta.env.VITE_DEV_LOGIN_PASSWORD
    ? {
        username: import.meta.env.VITE_DEV_LOGIN_USER,
        password: import.meta.env.VITE_DEV_LOGIN_PASSWORD,
      }
    : null;
