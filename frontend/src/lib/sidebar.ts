import { useSyncExternalStore } from 'react';

/** Whether the desktop sidebar is folded away. A UI preference, nothing sensitive. */
export const SIDEBAR_STORAGE_KEY = 'txat-sidebar';

/** Same breakpoint as Tailwind's `md`: below it the sidebar is an overlay panel instead. */
export const DESKTOP_QUERY = '(min-width: 768px)';

const listeners = new Set<() => void>();
// Used when storage is blocked (private mode, site data disabled): toggling still works for
// this page, it just isn't remembered.
let fallback = false;

function read(): boolean {
  try {
    const value = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (value === 'collapsed') return true;
    if (value === 'expanded') return false;
    return fallback;
  } catch {
    return fallback;
  }
}

export function isSidebarCollapsed(): boolean {
  return read();
}

export function setSidebarCollapsed(collapsed: boolean): void {
  fallback = collapsed;
  try {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? 'collapsed' : 'expanded');
  } catch {
    // not persisted; still applied for this page
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function isDesktop(): boolean {
  return window.matchMedia?.(DESKTOP_QUERY).matches ?? true;
}

/** The desktop sidebar's state and a function to fold or unfold it. */
export function useSidebarCollapsed(): { collapsed: boolean; toggle: () => void } {
  const collapsed = useSyncExternalStore(subscribe, isSidebarCollapsed, () => false);
  return { collapsed, toggle: () => setSidebarCollapsed(!collapsed) };
}

/** Ctrl+B (⌘B on macOS), without other modifiers: folds or unfolds the sidebar. */
export function isSidebarShortcut(event: KeyboardEvent): boolean {
  return (
    (event.ctrlKey || event.metaKey) &&
    !event.altKey &&
    !event.shiftKey &&
    !event.repeat &&
    !event.isComposing &&
    event.key.toLowerCase() === 'b'
  );
}

/** Test helper: forget the in-memory fallback. */
export function resetSidebarForTests(): void {
  fallback = false;
}
