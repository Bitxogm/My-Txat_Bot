import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ModelInfo } from '@/lib/api';
import { ModelSelect } from './model-select';

function model(name: string, remote: boolean): ModelInfo {
  return { name, size_bytes: 0, family: null, parameter_size: null, quantization: null, remote };
}

describe('ModelSelect', () => {
  it('groups local and cloud models so it is clear what leaves the network', () => {
    render(
      <ModelSelect
        models={[model('qwen3.5:9b', false), model('groq/openai/gpt-oss-120b', true)]}
        value="qwen3.5:9b"
        onChange={vi.fn()}
        status="ready"
        onReload={vi.fn()}
      />,
    );

    const local = screen.getByRole('group', { name: 'Local' });
    const cloud = screen.getByRole('group', { name: 'Nube (sale de tu red)' });
    expect(within(local).getByRole('option', { name: 'qwen3.5:9b' })).toBeInTheDocument();
    expect(
      within(cloud).getByRole('option', { name: 'groq/openai/gpt-oss-120b' }),
    ).toBeInTheDocument();
  });

  it('omits the cloud group when there are no cloud models', () => {
    render(
      <ModelSelect
        models={[model('qwen3.5:9b', false)]}
        value="qwen3.5:9b"
        onChange={vi.fn()}
        status="ready"
        onReload={vi.fn()}
      />,
    );

    expect(screen.queryByRole('group', { name: /Nube/ })).not.toBeInTheDocument();
  });
});
