import { StrictMode } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  createConversation,
  deleteAttachment,
  deleteConversation,
  getConversation,
  listAttachments,
  listConversations,
  listModels,
  listPersonalities,
  sendMessage,
  uploadAttachment,
  type Attachment,
  type Conversation,
  type ModelsResponse,
  type Personality,
  type StreamChatOptions,
} from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import { ChatPage } from './chat-page';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listModels: vi.fn(),
  listConversations: vi.fn(),
  listPersonalities: vi.fn(),
  listOsintSources: vi.fn(),
  createConversation: vi.fn(),
  getConversation: vi.fn(),
  deleteConversation: vi.fn(),
  sendMessage: vi.fn(),
  listAttachments: vi.fn(),
  uploadAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
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
      vision: false,
    },
    {
      name: 'b:8b',
      size_bytes: 1,
      family: null,
      parameter_size: null,
      quantization: null,
      remote: false,
      vision: false,
    },
  ],
  default_model: 'b:8b',
};

function conversation(id: string, title: string, model = 'a:7b'): Conversation {
  const at = '2026-11-20T10:00:00+00:00';
  return {
    id,
    title,
    model,
    created_at: at,
    updated_at: at,
    personality: { id: 'builtin-pentester', name: 'Pentester', icon: 'crosshair' },
  };
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

function personality(id: string, name: string, extra: Partial<Personality> = {}): Personality {
  return {
    id,
    name,
    icon: 'bot',
    description: `Descripción de ${name}`,
    system_prompt: 'x',
    temperature: null,
    top_p: null,
    num_ctx: null,
    default_model: null,
    builtin: true,
    created_at: '',
    updated_at: '',
    ...extra,
  };
}

const PERSONALITIES = [
  personality('builtin-mentor-ctf', 'Mentor CTF'),
  personality('builtin-pentester', 'Pentester', { default_model: 'a:7b' }),
];

beforeEach(() => {
  vi.mocked(listModels).mockResolvedValue(MODELS);
  vi.mocked(listPersonalities).mockResolvedValue({ personalities: PERSONALITIES });
  vi.mocked(listConversations).mockResolvedValue({ conversations: [OLD] });
  vi.mocked(createConversation).mockResolvedValue(conversation('n'.repeat(32), 'Nueva', 'b:8b'));
  vi.mocked(listAttachments).mockResolvedValue({ attachments: [] });
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
    expect(createConversation).toHaveBeenCalledWith({
      model: 'b:8b',
      personality_id: 'builtin-mentor-ctf',
    });
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
        {
          id: 1,
          role: 'user',
          content: 'pregunta',
          status: 'done',
          created_at: OLD.created_at,
          attachments: [],
        },
        {
          id: 2,
          role: 'assistant',
          content: 'a medias',
          status: 'stopped',
          attachments: [],
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

    expect(await screen.findByRole('radio', { name: /Mentor CTF/ })).toBeChecked();
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

describe('ChatPage personalities', () => {
  it('starts a new chat with Mentor CTF selected', async () => {
    await renderReady();

    expect(await screen.findByRole('radio', { name: /Mentor CTF/ })).toBeChecked();
    expect(screen.getByRole('radio', { name: /Pentester/ })).not.toBeChecked();
  });

  it('creates the conversation with the chosen personality and its default model', async () => {
    vi.mocked(sendMessage).mockResolvedValue({ model: 'a:7b', content: '' });
    const { user, select } = await renderReady();

    await user.click(await screen.findByRole('radio', { name: /Pentester/ }));
    expect(select).toHaveValue('a:7b');
    await user.type(messageBox(), 'hola{Enter}');

    await waitFor(() =>
      expect(createConversation).toHaveBeenCalledWith({
        model: 'a:7b',
        personality_id: 'builtin-pentester',
      }),
    );
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
  });

  it('shows the personality of an opened conversation, read-only', async () => {
    vi.mocked(getConversation).mockResolvedValue({ ...OLD, messages: [] });
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Notas de un CTF' }));

    const badge = await screen.findByTitle('Personalidad fijada al crear esta conversación');
    expect(badge).toHaveTextContent('Pentester');
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
  });

  it('opens the personalities page from the sidebar', async () => {
    const { user } = await renderReady();

    await user.click(screen.getByRole('button', { name: 'Personalidades' }));

    expect(await screen.findByRole('heading', { name: 'Personalidades' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Mensaje' })).not.toBeInTheDocument();
  });
});

describe('ChatPage settings navigation', () => {
  it('opens the OSINT sources page from the sidebar', async () => {
    const { listOsintSources } = await import('@/lib/api');
    vi.mocked(listOsintSources).mockResolvedValue({ sources: [] });
    const { user } = await renderReady();

    await user.click(screen.getByRole('button', { name: 'Fuentes OSINT' }));

    expect(await screen.findByRole('heading', { name: 'Fuentes OSINT' })).toBeInTheDocument();
  });
});

describe('ChatPage attachments', () => {
  function uploaded(id: string, filename: string, extra: Partial<Attachment> = {}): Attachment {
    return {
      id,
      filename,
      kind: 'text',
      mime: 'text/plain',
      size_bytes: 2048,
      truncated: false,
      sent: false,
      created_at: OLD.created_at,
      ...extra,
    };
  }

  function textFile(name: string): File {
    return new File(['22/tcp open ssh'], name, { type: 'text/plain' });
  }

  it('creates the conversation on the first file, uploads it and sends its id', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue(uploaded('f'.repeat(32), 'scan.nmap'));
    vi.mocked(sendMessage).mockResolvedValue({ model: 'b:8b', content: 'ok' });
    const { user } = await renderReady();

    await user.upload(screen.getByTestId('file-input'), textFile('scan.nmap'));

    const chips = await screen.findByRole('list', { name: 'Ficheros adjuntos' });
    expect(await within(chips).findByText('2 KB')).toBeInTheDocument();
    expect(createConversation).toHaveBeenCalledWith({
      model: 'b:8b',
      personality_id: 'builtin-mentor-ctf',
    });
    expect(uploadAttachment).toHaveBeenCalledWith(
      'n'.repeat(32),
      expect.any(File),
      expect.any(AbortSignal),
    );

    await user.type(messageBox(), 'analiza{Enter}');

    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith(
        'n'.repeat(32),
        { content: 'analiza', model: 'b:8b', attachment_ids: ['f'.repeat(32)] },
        expect.anything(),
      ),
    );
    const sent = await screen.findByRole('list', { name: 'Ficheros enviados' });
    expect(within(sent).getByText('scan.nmap')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Ficheros adjuntos' })).not.toBeInTheDocument();
  });

  it('uploads under StrictMode (mount, unmount, mount)', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue(uploaded('9'.repeat(32), 'a.txt'));
    const user = userEvent.setup();
    render(
      <StrictMode>
        <ChatPage username="void" onLogout={vi.fn()} />
      </StrictMode>,
    );
    const select = await screen.findByRole('combobox', { name: 'Modelo' });
    await waitFor(() => expect(select).toBeEnabled());

    await user.upload(screen.getByTestId('file-input'), textFile('a.txt'));

    expect(await screen.findByRole('button', { name: 'Quitar a.txt' })).toBeInTheDocument();
    expect(vi.mocked(uploadAttachment).mock.calls[0][2]?.aborted).toBe(false);
  });

  it('does not send while a file is still uploading', async () => {
    let finish: (value: Attachment) => void = () => {};
    vi.mocked(uploadAttachment).mockImplementation(
      () => new Promise((resolve) => (finish = resolve)),
    );
    const { user } = await renderReady();

    await user.upload(screen.getByTestId('file-input'), textFile('log.txt'));
    await user.type(messageBox(), 'hola');

    expect(await screen.findByText('subiendo…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled();

    finish(uploaded('a'.repeat(32), 'log.txt'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar' })).toBeEnabled());
  });

  it('drops a rejected file and shows the server message', async () => {
    const error = new ApiError({
      kind: 'unsupported_media_type',
      status: 415,
      code: 'UNSUPPORTED_MEDIA_TYPE',
      message: 'Tipo de fichero no admitido.',
      requestId: 'r1',
    });
    vi.mocked(uploadAttachment).mockRejectedValue(error);
    const { user } = await renderReady();

    await user.upload(screen.getByTestId('file-input'), textFile('notas.txt'));

    await waitFor(() => expect(notifyError).toHaveBeenCalledWith(error));
    expect(screen.queryByRole('list', { name: 'Ficheros adjuntos' })).not.toBeInTheDocument();
  });

  it('removes a pending file on the server', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue(uploaded('b'.repeat(32), 'a.md'));
    vi.mocked(deleteAttachment).mockResolvedValue();
    const { user } = await renderReady();
    await user.upload(screen.getByTestId('file-input'), textFile('a.md'));

    await user.click(await screen.findByRole('button', { name: 'Quitar a.md' }));

    expect(deleteAttachment).toHaveBeenCalledWith('n'.repeat(32), 'b'.repeat(32));
    expect(screen.queryByRole('list', { name: 'Ficheros adjuntos' })).not.toBeInTheDocument();
  });

  it('restores unsent files and shows sent ones when opening a conversation', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      ...OLD,
      messages: [
        {
          id: 1,
          role: 'user',
          content: 'mira',
          status: 'done',
          created_at: OLD.created_at,
          attachments: [
            {
              id: 'c'.repeat(32),
              filename: 'big.log',
              kind: 'text',
              size_bytes: 9,
              truncated: true,
            },
          ],
        },
      ],
    });
    vi.mocked(listAttachments).mockResolvedValue({
      attachments: [
        uploaded('c'.repeat(32), 'big.log', { sent: true }),
        uploaded('d'.repeat(32), 'pendiente.pdf', { kind: 'pdf' }),
      ],
    });
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Notas de un CTF' }));

    const sent = await screen.findByRole('list', { name: 'Ficheros enviados' });
    expect(within(sent).getByText('9 B · recortado')).toBeInTheDocument();
    const pending = await screen.findByRole('list', { name: 'Ficheros adjuntos' });
    expect(within(pending).getByText('pendiente.pdf')).toBeInTheDocument();
    expect(within(pending).queryByText('big.log')).not.toBeInTheDocument();
  });

  it('warns that files leave the network with a cloud model', async () => {
    vi.mocked(listModels).mockResolvedValue({
      models: [{ ...MODELS.models[0], name: 'groq/llama', remote: true }],
      default_model: 'groq/llama',
    });
    vi.mocked(uploadAttachment).mockResolvedValue(uploaded('e'.repeat(32), 'a.txt'));
    const { user } = await renderReady();

    await user.upload(screen.getByTestId('file-input'), textFile('a.txt'));

    expect(await screen.findByText(/saldrá de tu red/)).toBeInTheDocument();
  });

  function imageFile(name: string): File {
    return new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, { type: 'image/png' });
  }

  it('shows an image thumbnail and blocks sending to a model without vision', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue(
      uploaded('i'.repeat(32), 'captura.png', { kind: 'image', mime: 'image/png' }),
    );
    const { user } = await renderReady(); // b:8b, no vision

    await user.upload(screen.getByTestId('file-input'), imageFile('captura.png'));
    await user.type(messageBox(), 'qué ves');

    const chips = await screen.findByRole('list', { name: 'Ficheros adjuntos' });
    expect(within(chips).getByRole('presentation')).toHaveAttribute(
      'src',
      `/api/conversations/${'n'.repeat(32)}/attachments/${'i'.repeat(32)}/content`,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('b:8b no ve imágenes');
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled();
  });

  it('sends images to a vision model and shows them on the message', async () => {
    vi.mocked(listModels).mockResolvedValue({
      models: [{ ...MODELS.models[0], name: 'qwen', vision: true }],
      default_model: 'qwen',
    });
    vi.mocked(uploadAttachment).mockResolvedValue(
      uploaded('j'.repeat(32), 'reto.png', { kind: 'image', mime: 'image/png' }),
    );
    vi.mocked(sendMessage).mockResolvedValue({ model: 'qwen', content: 'veo un puerto' });
    const { user } = await renderReady();

    await user.upload(screen.getByTestId('file-input'), imageFile('reto.png'));
    await screen.findByRole('button', { name: 'Quitar reto.png' });
    await user.type(messageBox(), 'qué ves{Enter}');

    const sent = await screen.findByRole('list', { name: 'Imágenes enviadas' });
    const image = within(sent).getByRole('img', { name: 'reto.png' });
    expect(image).toHaveAttribute(
      'src',
      `/api/conversations/${'n'.repeat(32)}/attachments/${'j'.repeat(32)}/content`,
    );
    expect(image.closest('a')).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('warns that earlier images go to a cloud model with vision', async () => {
    vi.mocked(listModels).mockResolvedValue({
      models: [{ ...MODELS.models[0], name: 'groq/scout', remote: true, vision: true }],
      default_model: 'groq/scout',
    });
    vi.mocked(getConversation).mockResolvedValue({
      ...OLD,
      messages: [
        {
          id: 1,
          role: 'user',
          content: 'mira',
          status: 'done',
          created_at: OLD.created_at,
          attachments: [
            {
              id: 'k'.repeat(32),
              filename: 'a.png',
              kind: 'image',
              size_bytes: 9,
              truncated: false,
            },
          ],
        },
      ],
    });
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Notas de un CTF' }));

    expect(await screen.findByText(/imágenes recientes de esta conversación/)).toBeInTheDocument();
  });
});
