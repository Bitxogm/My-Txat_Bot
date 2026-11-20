import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './error-boundary';

function Boom(): never {
  throw new Error('Maximum call stack size exceeded');
}

describe('ErrorBoundary', () => {
  it('shows the fallback instead of unmounting everything', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    render(
      <div>
        <p>resto de la app</p>
        <ErrorBoundary fallback={<p>texto plano</p>}>
          <Boom />
        </ErrorBoundary>
      </div>,
    );

    expect(screen.getByText('texto plano')).toBeInTheDocument();
    expect(screen.getByText('resto de la app')).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
