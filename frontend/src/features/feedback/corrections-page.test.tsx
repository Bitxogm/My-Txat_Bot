import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  exportFeedback,
  listFeedback,
  rateMessage,
  unrateMessage,
  type Feedback,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import { CorrectionsPage } from './corrections-page';
import { PAGE_SIZE } from './use-corrections';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listFeedback: vi.fn(),
  rateMessage: vi.fn(),
  unrateMessage: vi.fn(),
  exportFeedback: vi.fn(),
}));
vi.mock('@/lib/notify-error', () => ({ notifyError: vi.fn() }));

function feedback(messageId: number, extra: Partial<Feedback> = {}): Feedback {
  return {
    message_id: messageId,
    conversation_id: 'c'.repeat(32),
    rating: -1,
    reasons: ['wrong_command'],
    correction: 'Es nmap -sV',
    question: '¿Qué flag detecta versiones?',
    question_files: [],
    answer: 'Usa --version-detection',
    model: 'qwen3.5:9b',
    model_approximate: false,
    provider: 'ollama',
    personality: 'Pentester',
    base_prompt_version: '0469a849',
    created_at: '2026-11-24T10:00:00+00:00',
    updated_at: '2026-11-24T10:00:00+00:00',
    ...extra,
  };
}

function renderPage(onOpenConversation = vi.fn()) {
  const user = userEvent.setup();
  render(
    <CorrectionsPage
      models={['qwen3.5:9b', 'groq/openai/gpt-oss-120b']}
      personalities={['General', 'Pentester']}
      onOpenConversation={onOpenConversation}
    />,
  );
  return { user, onOpenConversation };
}

beforeEach(() => {
  vi.mocked(listFeedback).mockResolvedValue({ items: [feedback(7)], total: 1 });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('CorrectionsPage', () => {
  it('shows question, answer and correction side by side', async () => {
    renderPage();

    const card = await screen.findByRole('article', { name: /^Valoración del/ });
    expect(within(card).getByRole('region', { name: 'Pregunta' })).toHaveTextContent(
      '¿Qué flag detecta versiones?',
    );
    expect(within(card).getByRole('region', { name: 'Respuesta' })).toHaveTextContent(
      'Usa --version-detection',
    );
    expect(within(card).getByRole('region', { name: 'Corrección' })).toHaveTextContent(
      'Es nmap -sV',
    );
    expect(within(card).getByText('Comando o flag erróneo')).toBeInTheDocument();
    expect(
      within(card).getByText(/qwen3\.5:9b · Pentester · capa base 0469a849/),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('1 valoración');
    expect(listFeedback).toHaveBeenCalledWith(
      {},
      { limit: PAGE_SIZE, offset: 0 },
      expect.any(AbortSignal),
    );
  });

  it('never renders the texts as HTML', async () => {
    vi.mocked(listFeedback).mockResolvedValue({
      items: [
        feedback(7, {
          correction: '<img src=x onerror=alert(1)><b>negrita</b>',
          answer: '**markdown** <script>x</script>',
        }),
      ],
      total: 1,
    });
    renderPage();

    const card = await screen.findByRole('article', { name: /^Valoración del/ });
    expect(within(card).getByRole('region', { name: 'Corrección' })).toHaveTextContent(
      '<img src=x onerror=alert(1)><b>negrita</b>',
    );
    expect(within(card).getByRole('region', { name: 'Respuesta' })).toHaveTextContent(
      '**markdown** <script>x</script>',
    );
    expect(card.querySelector('img, b, script, strong')).toBeNull();
  });

  it('marks an approximate model and an unknown base layer, and lists the files', async () => {
    vi.mocked(listFeedback).mockResolvedValue({
      items: [
        feedback(7, {
          model_approximate: true,
          base_prompt_version: null,
          question_files: ['scan.txt'],
        }),
      ],
      total: 1,
    });
    renderPage();

    const card = await screen.findByRole('article', { name: /^Valoración del/ });
    expect(within(card).getByText(/qwen3\.5:9b \(aproximado\)/)).toBeInTheDocument();
    expect(within(card).getByText(/capa base desconocido/)).toBeInTheDocument();
    expect(within(card).getByRole('region', { name: 'Pregunta' })).toHaveTextContent(
      '[Ficheros: scan.txt]',
    );
  });

  it('sends the chosen filters', async () => {
    const { user } = renderPage();
    await screen.findByRole('article', { name: /^Valoración del/ });

    await user.selectOptions(screen.getByLabelText('Valoración'), '-1');
    await user.selectOptions(screen.getByLabelText('Motivo'), 'too_long');
    await user.selectOptions(screen.getByLabelText('Modelo'), 'qwen3.5:9b');
    await user.selectOptions(screen.getByLabelText('Personalidad'), 'Pentester');
    await user.type(screen.getByLabelText('Desde'), '2026-11-01');
    await user.type(screen.getByLabelText('Hasta'), '2026-11-30');
    await user.click(screen.getByRole('button', { name: 'Filtrar' }));

    await waitFor(() =>
      expect(listFeedback).toHaveBeenLastCalledWith(
        {
          rating: -1,
          reason: 'too_long',
          model: 'qwen3.5:9b',
          personality: 'Pentester',
          from: '2026-11-01',
          to: '2026-11-30',
        },
        { limit: PAGE_SIZE, offset: 0 },
        expect.any(AbortSignal),
      ),
    );
    await user.click(screen.getByRole('button', { name: 'Limpiar' }));
    await waitFor(() =>
      expect(listFeedback).toHaveBeenLastCalledWith(
        {},
        { limit: PAGE_SIZE, offset: 0 },
        expect.any(AbortSignal),
      ),
    );
    expect(screen.getByLabelText('Valoración')).toHaveValue('');
  });

  it('loads more pages', async () => {
    vi.mocked(listFeedback)
      .mockResolvedValueOnce({ items: [feedback(9)], total: 2 })
      .mockResolvedValueOnce({ items: [feedback(8)], total: 2 });
    const { user } = renderPage();
    await screen.findByRole('article', { name: /^Valoración del/ });

    await user.click(screen.getByRole('button', { name: 'Cargar más' }));

    await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(2));
    expect(listFeedback).toHaveBeenLastCalledWith({}, { limit: PAGE_SIZE, offset: 1 });
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument();
  });

  it('edits a correction with the same form as the chat', async () => {
    vi.mocked(rateMessage).mockResolvedValue(feedback(7, { correction: 'Es nmap -sV -p-' }));
    const { user } = renderPage();
    const card = await screen.findByRole('article', { name: /^Valoración del/ });

    await user.click(within(card).getByRole('button', { name: 'Respuesta mejorable' }));
    const textarea = await screen.findByLabelText('¿Cuál sería la respuesta correcta?');
    expect(textarea).toHaveValue('Es nmap -sV');
    await user.type(textarea, ' -p-');
    await user.click(screen.getByRole('button', { name: 'Guardar' }));

    expect(rateMessage).toHaveBeenCalledWith(7, {
      rating: -1,
      reasons: ['wrong_command'],
      correction: 'Es nmap -sV -p-',
    });
    await waitFor(() =>
      expect(within(card).getByRole('region', { name: 'Corrección' })).toHaveTextContent(
        'Es nmap -sV -p-',
      ),
    );
  });

  it('deletes a rating after confirming', async () => {
    vi.mocked(unrateMessage).mockResolvedValue(undefined);
    const { user } = renderPage();
    const card = await screen.findByRole('article', { name: /^Valoración del/ });

    await user.click(within(card).getByRole('button', { name: 'Borrar valoración' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(unrateMessage).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole('button', { name: 'Borrar' }));

    expect(unrateMessage).toHaveBeenCalledWith(7);
    await waitFor(() => expect(screen.queryByRole('article')).not.toBeInTheDocument());
    expect(screen.getByRole('status')).toHaveTextContent('0 valoraciones');
  });

  it('opens the original conversation at the rated reply', async () => {
    const { user, onOpenConversation } = renderPage();
    const card = await screen.findByRole('article', { name: /^Valoración del/ });

    await user.click(within(card).getByRole('button', { name: 'Ir a la conversación' }));

    expect(onOpenConversation).toHaveBeenCalledWith('c'.repeat(32), 7);
  });

  it('exports the filtered ratings as a JSONL download', async () => {
    const blob = new Blob(['{}\n'], { type: 'application/x-ndjson' });
    vi.mocked(exportFeedback).mockResolvedValue({
      blob,
      filename: 'txat-feedback-2026-11-24.jsonl',
    });
    const createObjectURL = vi.fn(() => 'blob:x');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const { user } = renderPage();
    await screen.findByRole('article', { name: /^Valoración del/ });

    await user.selectOptions(screen.getByLabelText('Valoración'), '-1');
    await user.click(screen.getByRole('button', { name: 'Filtrar' }));
    await user.click(screen.getByRole('button', { name: 'Exportar JSONL' }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(exportFeedback).toHaveBeenCalledWith(expect.objectContaining({ rating: -1 }));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:x');
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe('txat-feedback-2026-11-24.jsonl');
    click.mockRestore();
    vi.unstubAllGlobals();
  });

  it('a failed export is notified', async () => {
    const failure = new ApiError({
      kind: 'unauthorized',
      status: 401,
      code: 'UNAUTHORIZED',
      message: 'Inicia sesión',
      requestId: 'r1',
    });
    vi.mocked(exportFeedback).mockRejectedValue(failure);
    const { user } = renderPage();
    await screen.findByRole('article', { name: /^Valoración del/ });

    await user.click(screen.getByRole('button', { name: 'Exportar JSONL' }));

    await waitFor(() => expect(notifyError).toHaveBeenCalledWith(failure));
  });

  it('says when there is nothing to show', async () => {
    vi.mocked(listFeedback).mockResolvedValue({ items: [], total: 0 });
    renderPage();

    expect(await screen.findByText(/No hay valoraciones con estos filtros/)).toBeInTheDocument();
  });
});
