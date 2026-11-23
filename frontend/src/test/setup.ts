import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
});

// jsdom lacks matchMedia; Sonner and next-themes read it for the system color scheme.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// jsdom lacks ResizeObserver; Radix (Checkbox, Switch) uses it to measure elements.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!('ResizeObserver' in window)) {
  Object.defineProperty(window, 'ResizeObserver', { writable: true, value: ResizeObserverStub });
}

// jsdom lacks pointer capture and scrollIntoView; Radix Select uses them to open and highlight.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
