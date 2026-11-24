import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  isSidebarCollapsed,
  isSidebarShortcut,
  resetSidebarForTests,
  setSidebarCollapsed,
  SIDEBAR_STORAGE_KEY,
  useSidebarCollapsed,
} from './sidebar';

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  resetSidebarForTests();
});

function key(init: KeyboardEventInit) {
  return new KeyboardEvent('keydown', init);
}

describe('sidebar preference', () => {
  it('is unfolded by default', () => {
    expect(isSidebarCollapsed()).toBe(false);
  });

  it('remembers the choice', () => {
    setSidebarCollapsed(true);

    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('collapsed');
    expect(isSidebarCollapsed()).toBe(true);
    setSidebarCollapsed(false);
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('expanded');
  });

  it('ignores an unknown stored value', () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, '<script>');

    expect(isSidebarCollapsed()).toBe(false);
  });

  it('still toggles, silently, when storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    const error = vi.spyOn(console, 'error');
    const { result } = renderHook(() => useSidebarCollapsed());

    expect(result.current.collapsed).toBe(false);
    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(true);
    act(() => result.current.toggle());
    expect(result.current.collapsed).toBe(false);
    expect(error).not.toHaveBeenCalled();
  });

  it('the hook follows changes made elsewhere', () => {
    const { result } = renderHook(() => useSidebarCollapsed());

    act(() => setSidebarCollapsed(true));

    expect(result.current.collapsed).toBe(true);
  });
});

describe('sidebar shortcut', () => {
  it.each([
    [{ key: 'b', ctrlKey: true }, true],
    [{ key: 'B', ctrlKey: true }, true],
    [{ key: 'b', metaKey: true }, true],
    [{ key: 'b' }, false],
    [{ key: 'b', ctrlKey: true, shiftKey: true }, false],
    [{ key: 'b', ctrlKey: true, altKey: true }, false],
    [{ key: 'b', ctrlKey: true, repeat: true }, false],
    [{ key: 'n', ctrlKey: true }, false],
  ])('%o -> %s', (init, expected) => {
    expect(isSidebarShortcut(key(init))).toBe(expected);
  });
});
