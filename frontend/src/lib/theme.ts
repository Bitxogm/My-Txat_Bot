import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';

/** Same key as public/theme-init.js, which applies the theme before React loads. */
export const THEME_STORAGE_KEY = 'txat-theme';

const DARK_QUERY = '(prefers-color-scheme: dark)';
const listeners = new Set<() => void>();

/** The user's explicit choice, or null to follow the system. A UI preference, nothing sensitive. */
function savedTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null; // storage blocked (private mode, site data disabled)
  }
}

function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? 'dark' : 'light';
}

export function currentTheme(): Theme {
  return savedTheme() ?? systemTheme();
}

function apply(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
}

function notify(): void {
  apply(currentTheme());
  for (const listener of listeners) listener();
}

export function setTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // not persisted; still applied for this page
  }
  apply(theme);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // While the user hasn't chosen, follow changes of the system setting.
  const media = window.matchMedia?.(DARK_QUERY);
  const onChange = () => {
    if (savedTheme() === null) notify();
  };
  media?.addEventListener?.('change', onChange);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener?.('change', onChange);
  };
}

/** The theme in use and a function to switch between light and dark. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const theme = useSyncExternalStore(subscribe, currentTheme, () => 'light' as const);
  return { theme, toggle: () => setTheme(theme === 'dark' ? 'light' : 'dark') };
}
