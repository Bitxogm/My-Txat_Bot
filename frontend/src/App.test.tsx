import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listModels: vi.fn().mockResolvedValue({ models: [], default_model: null }),
}));

describe('App', () => {
  it('renders the chat screen', async () => {
    render(<App />);

    expect(screen.getByRole('heading', { name: 'Txat_bot' })).toBeInTheDocument();
    expect(await screen.findByText('Escribe un mensaje para empezar.')).toBeInTheDocument();
  });
});
