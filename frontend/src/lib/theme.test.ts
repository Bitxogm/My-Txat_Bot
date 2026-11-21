import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { currentTheme, setTheme, THEME_STORAGE_KEY, useTheme } from './theme';

function mockSystemDark(dark: boolean) {
  vi.mocked(window.matchMedia).mockImplementation(
    (query: string) =>
      ({
        matches: dark && query.includes('dark'),
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove('dark');
  mockSystemDark(false);
});

describe('theme', () => {
  it('follows the system until the user chooses', () => {
    mockSystemDark(true);

    expect(currentTheme()).toBe('dark');
  });

  it('a saved choice wins over the system and is applied to <html>', () => {
    mockSystemDark(true);

    setTheme('light');

    expect(currentTheme()).toBe('light');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');
    expect(document.documentElement).not.toHaveClass('dark');
  });

  it('toggles between day and night and remembers it', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('light');

    act(() => result.current.toggle());

    expect(result.current.theme).toBe('dark');
    expect(document.documentElement).toHaveClass('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('still works when storage is blocked', () => {
    const blocked = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });

    expect(currentTheme()).toBe('light');
    blocked.mockRestore();
  });
});
