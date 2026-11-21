import { render } from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PwaUpdater, UPDATE_CHECK_MS } from './pwa-updater';

const updateServiceWorker = vi.fn(async () => undefined);
let needRefresh = false;

let onRegistered: ((url: string, registration?: { update: () => Promise<void> }) => void) | null =
  null;

vi.mock('virtual:pwa-register/react', () => ({
  useRegisterSW: (options?: { onRegisteredSW?: typeof onRegistered }) => {
    onRegistered = options?.onRegisteredSW ?? null;
    return {
      needRefresh: [needRefresh, vi.fn()],
      offlineReady: [false, vi.fn()],
      updateServiceWorker,
    };
  },
}));
vi.mock('sonner', () => ({ toast: vi.fn() }));

afterEach(() => {
  vi.clearAllMocks();
  needRefresh = false;
});

describe('PwaUpdater', () => {
  it('stays quiet while there is no new version', () => {
    render(<PwaUpdater />);

    expect(toast).not.toHaveBeenCalled();
  });

  it('offers to reload when a new version is waiting, and only reloads on click', () => {
    needRefresh = true;
    render(<PwaUpdater />);

    expect(toast).toHaveBeenCalledOnce();
    const [title, options] = vi.mocked(toast).mock.calls[0];
    expect(title).toBe('Nueva versión disponible');
    expect(updateServiceWorker).not.toHaveBeenCalled();

    const action = options?.action as { label: string; onClick: () => void };
    expect(action.label).toBe('Recargar');
    action.onClick();
    expect(updateServiceWorker).toHaveBeenCalledWith(true);
  });

  it('checks for a new version every hour', () => {
    vi.useFakeTimers();
    const update = vi.fn(async () => undefined);
    render(<PwaUpdater />);

    onRegistered?.('/sw.js', { update });
    vi.advanceTimersByTime(UPDATE_CHECK_MS);

    expect(update).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });
});
