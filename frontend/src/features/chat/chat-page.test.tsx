import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  listModels,
  streamChat,
  type ModelsResponse,
  type StreamChatOptions,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import { ChatPage } from './chat-page';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listModels: vi.fn(),
  streamChat: vi.fn(),
}));
vi.mock('@/lib/notify-error', () => ({ notifyError: vi.fn() }));

const listModelsMock = vi.mocked(listModels);
const streamChatMock = vi.mocked(streamChat);

const MODELS: ModelsResponse = {
  models: [
    { name: 'a:7b', size_bytes: 1, family: null, parameter_size: '7B', quantization: 'Q4_K_M' },
    { name: 'b:8b', size_bytes: 1, family: null, parameter_size: null, quantization: null },
  ],
  default_model: 'b:8b',
};

function abortError() {
  return new DOMException('aborted', 'AbortError');
}

async function renderReady() {
  const user = userEvent.setup();
  render(<ChatPage />);
  const select = await screen.findByRole('combobox', { name: 'Modelo' });
  await waitFor(() => expect(select).toBeEnabled());
  return { user, select };
}

beforeEach(() => {
  listModelsMock.mockResolvedValue(MODELS);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('ChatPage', () => {
  it('selects the default model', async () => {
    const { select } = await renderReady();

    expect(select).toHaveValue('b:8b');
    expect(within(select).getByRole('option', { name: 'a:7b (7B · Q4_K_M)' })).toBeInTheDocument();
  });

  it('streams the reply and sends the history with the chosen model', async () => {
    streamChatMock.mockImplementation(async (_body, { onToken }: StreamChatOptions) => {
      onToken('Ho');
      onToken('la');
      return { model: 'a:7b', content: 'Hola' };
    });
    const { user, select } = await renderReady();

    await user.selectOptions(select, 'a:7b');
    await user.type(screen.getByRole('textbox', { name: 'Mensaje' }), 'hola{Enter}');

    expect(await screen.findByText('Hola')).toBeInTheDocument();
    expect(screen.getByText('hola')).toBeInTheDocument();
    expect(streamChatMock).toHaveBeenCalledWith(
      { model: 'a:7b', messages: [{ role: 'user', content: 'hola' }] },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByRole('textbox', { name: 'Mensaje' })).toHaveValue('');
  });

  it('keeps Shift+Enter as a new line', async () => {
    const { user } = await renderReady();
    const box = screen.getByRole('textbox', { name: 'Mensaje' });

    await user.type(box, 'a{Shift>}{Enter}{/Shift}b');

    expect(box).toHaveValue('a\nb');
    expect(streamChatMock).not.toHaveBeenCalled();
  });

  it('stops a reply in progress', async () => {
    streamChatMock.mockImplementation(
      (_body, { signal, onToken }: StreamChatOptions) =>
        new Promise((_resolve, reject) => {
          onToken('parcial');
          signal?.addEventListener('abort', () => reject(abortError()));
        }),
    );
    const { user } = await renderReady();

    await user.type(screen.getByRole('textbox', { name: 'Mensaje' }), 'cuenta{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Detener' }));

    expect(await screen.findByText('Respuesta detenida.')).toBeInTheDocument();
    expect(screen.getByText('parcial')).toBeInTheDocument();
    expect(notifyError).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeInTheDocument();
  });

  it('shows the error and leaves failed turns out of the next request', async () => {
    const failure = new ApiError({
      kind: 'server',
      status: 503,
      code: 'MODEL_UNAVAILABLE',
      message: 'Caído',
      requestId: 'r1',
    });
    streamChatMock.mockRejectedValueOnce(failure);
    streamChatMock.mockResolvedValueOnce({ model: 'b:8b', content: '' });
    const { user } = await renderReady();
    const box = screen.getByRole('textbox', { name: 'Mensaje' });

    await user.type(box, 'uno{Enter}');
    expect(await screen.findByText('No se pudo completar la respuesta.')).toBeInTheDocument();
    expect(notifyError).toHaveBeenCalledWith(failure);

    await user.type(box, 'dos{Enter}');
    await waitFor(() => expect(streamChatMock).toHaveBeenCalledTimes(2));
    expect(streamChatMock.mock.calls[1][0].messages).toEqual([
      { role: 'user', content: 'uno' },
      { role: 'user', content: 'dos' },
    ]);
  });

  it('disables the composer and offers a reload when models fail to load', async () => {
    listModelsMock.mockReset();
    listModelsMock.mockRejectedValueOnce(
      new ApiError({
        kind: 'network',
        status: null,
        code: 'NETWORK_ERROR',
        message: 'x',
        requestId: null,
      }),
    );
    listModelsMock.mockResolvedValueOnce(MODELS);
    const user = userEvent.setup();
    render(<ChatPage />);

    await waitFor(() => expect(notifyError).toHaveBeenCalled());
    expect(screen.getByRole('textbox', { name: 'Mensaje' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Recargar modelos' }));

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Modelo' })).toHaveValue('b:8b'),
    );
    expect(screen.getByRole('textbox', { name: 'Mensaje' })).toBeEnabled();
  });

  it('starts a new conversation', async () => {
    streamChatMock.mockResolvedValue({ model: 'b:8b', content: '' });
    const { user } = await renderReady();

    await user.type(screen.getByRole('textbox', { name: 'Mensaje' }), 'hola{Enter}');
    expect(await screen.findByText('hola')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }));

    expect(screen.getByText('Escribe un mensaje para empezar.')).toBeInTheDocument();
  });
});
