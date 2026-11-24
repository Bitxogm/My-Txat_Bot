import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Personality } from '@/lib/api';
import { PersonalitySelect } from './personality-select';

const GENERAL: Personality = {
  id: 'builtin-general',
  name: 'General',
  icon: 'message-circle',
  description: 'Responde de forma directa',
  system_prompt: 'x',
  temperature: null,
  top_p: null,
  num_ctx: null,
  default_model: null,
  builtin: true,
  created_at: '',
  updated_at: '',
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('PersonalitySelect', () => {
  it('stays controlled while the personalities load (no React/Radix warning)', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const props = { value: GENERAL.id, onChange: vi.fn(), locked: false, fixed: null };

    const { rerender } = render(<PersonalitySelect personalities={[]} {...props} />);
    expect(screen.getByRole('combobox', { name: 'Personalidad' })).toHaveTextContent(
      'Personalidad',
    );
    rerender(<PersonalitySelect personalities={[GENERAL]} {...props} />);

    expect(screen.getByRole('combobox', { name: 'Personalidad' })).toHaveTextContent('General');
    const calls = [...warn.mock.calls, ...error.mock.calls].map((args) => String(args[0]));
    expect(calls.filter((message) => /uncontrolled|controlled/.test(message))).toEqual([]);
  });
});
