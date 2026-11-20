/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Dev-only quick login, written by `uv run python -m app.cli dev-login` to .env.local. */
  readonly VITE_DEV_LOGIN_USER?: string;
  readonly VITE_DEV_LOGIN_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
