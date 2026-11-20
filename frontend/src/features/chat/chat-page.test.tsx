import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  listModels,
  sendMessage,
  type Conversation,
  type ModelsResponse,
  type StreamChatOptions,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import { ChatPage } from './chat-page';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listModels: vi.fn(),
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversation: vi.fn(),
  deleteConversation: vi.fn(),
  sendMessage: vi.fn(),
}));
vi.mock('@/lib/notify-error', () => ({ notifyError: vi.fn() }));

const MODELS: ModelsResponse = {
  models: [
    {
      name: 'a:7b',
      size_bytes: 1,
      family: null,
      parameter_size: '7B',
      quantization: 'Q4_K_M',
      remote: false,
    },
    {
      name: 'b:8b',
      size_bytes: 1,
      family: null,
      parameter_size: null,
      quantization: null,
      remote: false,
    },
  ],
  default_model: 'b:8b',
};

function conversation(id: string, title: string, model = 'a:7b'): Conversation {
  const at = '2026-11-20T10:00:00+00:00';
  return { id, title, model, created_at: at, updated_at: at };
}

const OLD = conversation('c'.repeat(32), 'Notas de un CTF');

function abortError() {
  return new DOMException('aborted', 'AbortError');
}

async function renderReady() {
  const user = userEvent.setup();
  render(<ChatPage username="void" onLogout={vi.fn()} />);
  const select = await screen.findByRole('combobox', { name: 'Modelo' });
  await waitFor(() => expect(select).toBeEnabled());
  return { user, select };
}

function messageBox() {
  return screen.getByRole('textbox', { name: 'Mensaje' });
}

beforeEach(() => {
  vi.mocked(listModels).mockResolvedValue(MODELS);
  vi.mocked(listConversations).mockResolvedValue({ conversations: [OLD] });
  vi.mocked(createConversation).mockResolvedValue(conversation('n'.repeat(32), 'Nueva', 'b:8b'));
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ChatPage', () => {
  it('selects the default model and lists saved conversations', async () => {
    const { select } = await renderReady();

    expect(select).toHaveValue('b:8b');
    expect(await screen.findByRole('button', { name: 'Notas de un CTF' })).toBeInTheDocument();
  });

  it('creates a conversation on the first message and streams the reply', async () => {
    vi.mocked(sendMessage).mockImplementation(
      async (_id, _body, { onToken }: StreamChatOptions) => {
        onToken('Ho');
        onToken('la');
        return { model: 'b:8b', content: 'Hola' };
      },
    );
    const { user } = await renderReady();

    await user.type(messageBox(), 'hola{Enter}');

    expect(await screen.findByText('Hola')).toBeInTheDocument();
    expect(createConversation).toHaveBeenCalledWith({ model: 'b:8b' });
    expect(sendMessage).toHaveBeenCalledWith(
      'n'.repeat(32),
      { content: 'hola', model: 'b:8b' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await waitFor(() => expect(vi.mocked(listConversations).mock.calls.length).toBeGreaterThan(1));
  });

  it('opens a saved conversation with its messages and model, and keeps sending to it', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      ...OLD,
      messages: [
        { id: 1, role: 'user', content: 'pregunta', status: 'done', created_at: OLD.created_at },
        {
          id: 2,
          role: 'assistant',
          content: 'a medias',
          status: 'stopped',
          created_at: OLD.created_at,
        },
      ],
    });
    vi.mocked(sendMessage).mockResolvedValue({ model: 'a:7b', content: '' });
    const { user, select } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Notas de un CTF' }));

    expect(await screen.findByText('pregunta')).toBeInTheDocument();
    expect(screen.getByText('Respuesta detenida.')).toBeInTheDocument();
    expect(select).toHaveValue('a:7b');
    expect(screen.getByRole('button', { name: 'Notas de un CTF' })).toHaveAttribute(
      'aria-current',
      'page',
    );

    await user.type(messageBox(), 'sigue{Enter}');
    await waitFor(() => expect(sendMessage).toHaveBeenCalled());
    expect(createConversation).not.toHaveBeenCalled();
    expect(vi.mocked(sendMessage).mock.calls[0][0]).toBe(OLD.id);
  });

  it('keeps Shift+Enter as a new line', async () => {
    const { user } = await renderReady();

    await user.type(messageBox(), 'a{Shift>}{Enter}{/Shift}b');

    expect(messageBox()).toHaveValue('a\nb');
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it('stops a reply in progress', async () => {
    vi.mocked(sendMessage).mockImplementation(
      (_id, _body, { signal, onToken }: StreamChatOptions) =>
        new Promise((_resolve, reject) => {
          onToken('parcial');
          signal?.addEventListener('abort', () => reject(abortError()));
        }),
    );
    const { user } = await renderReady();

    await user.type(messageBox(), 'cuenta{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Detener' }));

    expect(await screen.findByText('Respuesta detenida.')).toBeInTheDocument();
    expect(screen.getByText('parcial')).toBeInTheDocument();
    expect(notifyError).not.toHaveBeenCalled();
  });

  it('shows stream errors on the turn', async () => {
    const failure = new ApiError({
      kind: 'server',
      status: 503,
      code: 'MODEL_UNAVAILABLE',
      message: 'Caído',
      requestId: 'r1',
    });
    vi.mocked(sendMessage).mockRejectedValueOnce(failure);
    const { user } = await renderReady();

    await user.type(messageBox(), 'uno{Enter}');

    expect(await screen.findByText('No se pudo completar la respuesta.')).toBeInTheDocument();
    expect(notifyError).toHaveBeenCalledWith(failure);
  });

  it('starts a new conversation', async () => {
    vi.mocked(sendMessage).mockResolvedValue({ model: 'b:8b', content: '' });
    const { user } = await renderReady();
    await user.type(messageBox(), 'hola{Enter}');
    expect(await screen.findByText('hola')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }));

    expect(screen.getByText('Escribe un mensaje para empezar.')).toBeInTheDocument();
  });

  it('deletes a conversation after confirming', async () => {
    vi.mocked(deleteConversation).mockResolvedValue(undefined);
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Borrar «Notas de un CTF»' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(/No se puede deshacer/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Borrar' }));

    await waitFor(() => expect(deleteConversation).toHaveBeenCalledWith(OLD.id));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Notas de un CTF' })).not.toBeInTheDocument(),
    );
  });

  it('keeps the conversation if the delete is cancelled', async () => {
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Borrar «Notas de un CTF»' }));
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancelar' }),
    );

    expect(deleteConversation).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Notas de un CTF' })).toBeInTheDocument();
  });

  it('disables the composer and offers a reload when models fail to load', async () => {
    vi.mocked(listModels).mockReset();
    vi.mocked(listModels)
      .mockRejectedValueOnce(
        new ApiError({
          kind: 'network',
          status: null,
          code: 'NETWORK_ERROR',
          message: 'x',
          requestId: null,
        }),
      )
      .mockResolvedValueOnce(MODELS);
    const user = userEvent.setup();
    render(<ChatPage username="void" onLogout={vi.fn()} />);

    await waitFor(() => expect(notifyError).toHaveBeenCalled());
    expect(messageBox()).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Recargar modelos' }));

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Modelo' })).toHaveValue('b:8b'),
    );
    expect(messageBox()).toBeEnabled();
  });
});
