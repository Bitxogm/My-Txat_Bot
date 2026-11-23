import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Personality } from '@/lib/api';
import { PersonalityCards } from './personality-cards';

function personality(id: string, name: string, builtin: boolean): Personality {
  return {
    id,
    name,
    icon: 'message-circle',
    description: `Descripción de ${name}`,
    system_prompt: 'x',
    temperature: null,
    top_p: null,
    num_ctx: null,
    default_model: null,
    builtin,
    created_at: '',
    updated_at: '',
  };
}

describe('PersonalityCards', () => {
  it('shows each personality as a card with its kind, details and actions', () => {
    render(
      <PersonalityCards
        personalities={[
          personality('builtin-general', 'General', true),
          personality('mine', 'Mía', false),
        ]}
        details={(p) => <span>detalle {p.id}</span>}
        actions={(p) => <button type="button">Acción {p.name}</button>}
      />,
    );

    const list = screen.getByRole('list', { name: 'Lista de personalidades' });
    const general = within(list).getByRole('listitem', { name: 'General' });
    expect(within(general).getByText('Incorporada')).toBeInTheDocument();
    expect(within(general).getByText('Descripción de General')).toBeInTheDocument();
    expect(within(general).getByText('detalle builtin-general')).toBeInTheDocument();
    expect(within(general).getByRole('button', { name: 'Acción General' })).toBeInTheDocument();
    const mine = within(list).getByRole('listitem', { name: 'Mía' });
    expect(within(mine).getByText('Propia')).toBeInTheDocument();
  });
});
