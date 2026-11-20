import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ModelInfo, Personality } from '@/lib/api';
import { PersonalityPicker } from './personality-picker';

function personality(id: string, name: string, default_model: string | null = null): Personality {
  return {
    id,
    name,
    icon: 'flag',
    description: `Sobre ${name}`,
    system_prompt: 'x',
    temperature: null,
    top_p: null,
    num_ctx: null,
    default_model,
    builtin: true,
    created_at: '',
    updated_at: '',
  };
}

const MODELS: ModelInfo[] = [
  {
    name: 'groq/openai/gpt-oss-120b',
    size_bytes: 0,
    family: null,
    parameter_size: null,
    quantization: null,
    remote: true,
  },
];

describe('PersonalityPicker', () => {
  it('marks the selected personality and reports clicks', async () => {
    const onChange = vi.fn();
    const items = [personality('a', 'Mentor CTF'), personality('b', 'Pentester')];
    render(<PersonalityPicker personalities={items} value="a" onChange={onChange} models={[]} />);

    expect(screen.getByRole('radio', { name: /Mentor CTF/ })).toBeChecked();
    await userEvent.setup().click(screen.getByRole('radio', { name: /Pentester/ }));

    expect(onChange).toHaveBeenCalledWith(items[1]);
  });

  it('warns when the personality defaults to a cloud model', () => {
    render(
      <PersonalityPicker
        personalities={[personality('a', 'Nube', 'groq/openai/gpt-oss-120b')]}
        value="a"
        onChange={vi.fn()}
        models={MODELS}
      />,
    );

    expect(screen.getByText(/saldrá de tu red/)).toBeInTheDocument();
  });
});
