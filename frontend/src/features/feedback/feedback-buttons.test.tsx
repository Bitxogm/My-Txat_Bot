import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { MessageFeedback } from '@/lib/api';
import { FeedbackButtons } from './feedback-buttons';
import { MAX_CORRECTION_CHARS } from './reasons';

function setup(feedback: MessageFeedback | null = null) {
  const onRate = vi.fn<(f: MessageFeedback | null) => Promise<boolean>>().mockResolvedValue(true);
  render(<FeedbackButtons feedback={feedback} onRate={onRate} />);
  return { onRate, user: userEvent.setup() };
}

const up = () => screen.getByRole('button', { name: 'Respuesta útil' });
const down = () => screen.getByRole('button', { name: 'Respuesta mejorable' });

describe('FeedbackButtons', () => {
  it('saves 👍 at once and removes it with a second click', async () => {
    const { onRate, user } = setup();
    expect(up()).toHaveAttribute('aria-pressed', 'false');

    await user.click(up());
    expect(onRate).toHaveBeenLastCalledWith({ rating: 1, reasons: [], correction: null });
  });

  it('removes 👍 when it is already pressed', async () => {
    const { onRate, user } = setup({ rating: 1, reasons: [], correction: null });
    expect(up()).toHaveAttribute('aria-pressed', 'true');

    await user.click(up());

    expect(onRate).toHaveBeenCalledWith(null);
  });

  it('👎 opens the form and sends the chosen reasons and correction', async () => {
    const { onRate, user } = setup();

    await user.click(down());
    const dialog = await screen.findByRole('dialog', { name: '¿Qué falla en esta respuesta?' });
    expect(onRate).not.toHaveBeenCalled();
    await user.click(screen.getByLabelText('Comando o flag erróneo'));
    await user.click(screen.getByLabelText('Inventado o incorrecto'));
    await user.type(screen.getByLabelText('¿Cuál sería la respuesta correcta?'), 'Es nmap -sV');
    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    // Reasons keep the form's order, not the clicking order.
    expect(onRate).toHaveBeenCalledWith({
      rating: -1,
      reasons: ['incorrect', 'wrong_command'],
      correction: 'Es nmap -sV',
    });
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
  });

  it('everything in the form is optional', async () => {
    const { onRate, user } = setup();

    await user.click(down());
    await user.click(await screen.findByRole('button', { name: 'Guardar' }));

    expect(onRate).toHaveBeenCalledWith({ rating: -1, reasons: [], correction: null });
  });

  it('cancelling the form saves nothing', async () => {
    const { onRate, user } = setup();

    await user.click(down());
    await user.click(await screen.findByRole('button', { name: 'Cancelar' }));

    expect(onRate).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('editing loads what was saved and can remove the rating', async () => {
    const { onRate, user } = setup({
      rating: -1,
      reasons: ['too_long'],
      correction: 'Más corta',
    });
    expect(down()).toHaveAttribute('aria-pressed', 'true');

    await user.click(down());

    expect(await screen.findByLabelText('Demasiado largo')).toBeChecked();
    expect(screen.getByLabelText('Incompleto')).not.toBeChecked();
    expect(screen.getByLabelText('¿Cuál sería la respuesta correcta?')).toHaveValue('Más corta');
    await user.click(screen.getByRole('button', { name: 'Quitar valoración' }));
    expect(onRate).toHaveBeenCalledWith(null);
  });

  it('a new 👎 has no remove option', async () => {
    const { user } = setup();

    await user.click(down());

    await screen.findByRole('dialog');
    expect(screen.queryByRole('button', { name: 'Quitar valoración' })).not.toBeInTheDocument();
  });

  it('limits the correction to 4000 characters and shows the count', async () => {
    const { user } = setup();

    await user.click(down());
    const textarea = await screen.findByLabelText('¿Cuál sería la respuesta correcta?');

    expect(textarea).toHaveAttribute('maxLength', String(MAX_CORRECTION_CHARS));
    await user.type(textarea, 'hola');
    expect(screen.getByText(`4 / ${MAX_CORRECTION_CHARS}`)).toBeInTheDocument();
  });

  it('works with the keyboard: Tab, Space and Escape', async () => {
    const { onRate, user } = setup();

    await user.tab();
    expect(up()).toHaveFocus();
    await user.keyboard(' ');
    expect(onRate).toHaveBeenCalledWith({ rating: 1, reasons: [], correction: null });
    await user.tab();
    expect(down()).toHaveFocus();
    await user.keyboard('{Enter}');
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(onRate).toHaveBeenCalledTimes(1);
  });

  it('keeps the form open when saving fails', async () => {
    const { onRate, user } = setup();
    onRate.mockResolvedValue(false);

    await user.click(down());
    await user.click(await screen.findByRole('button', { name: 'Guardar' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
