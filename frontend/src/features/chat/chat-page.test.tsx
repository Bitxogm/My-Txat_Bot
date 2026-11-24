import { StrictMode } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  countConversationFeedback,
  createConversation,
  deleteAttachment,
  deleteConversation,
  getConversation,
  listAttachments,
  listConversations,
  listModels,
  listPersonalities,
  rateMessage,
  sendMessage,
  setConversationPersonality,
  unrateMessage,
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
  setConversationPersonality: vi.fn(),
  listAttachments: vi.fn(),
  uploadAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
  rateMessage: vi.fn(),
  unrateMessage: vi.fn(),
  countConversationFeedback: vi.fn(),
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
      provider: 'ollama',
    },
    {
      name: 'b:8b',
      size_bytes: 1,
      family: null,
      parameter_size: null,
      quantization: null,
      remote: false,
      vision: false,
      provider: 'ollama',
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

function personalityTrigger() {
  return screen.findByRole('combobox', { name: 'Personalidad' });
}

/** Through the keyboard, like a screen-reader user (Radix Select opens with Enter). */
async function choosePersonality(user: ReturnType<typeof userEvent.setup>, name: string) {
  // The composer takes the focus once the models are loaded; wait for it before moving on.
  await waitFor(() => expect(messageBox()).toHaveFocus());
  const trigger = await personalityTrigger();
  trigger.focus();
  await user.keyboard('{Enter}');
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  // Typeahead to the option and Enter, all by keyboard.
  await user.keyboard(name);
  await user.keyboard('{Enter}');
}

function lockedPersonality() {
  return screen.getByLabelText(/^Personalidad: /);
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
  personality('builtin-general', 'General'),
  personality('builtin-mentor-ctf', 'Mentor CTF'),
  personality('builtin-pentester', 'Pentester', { default_model: 'a:7b' }),
];

beforeEach(() => {
  vi.mocked(listModels).mockResolvedValue(MODELS);
  vi.mocked(listPersonalities).mockResolvedValue({ personalities: PERSONALITIES });
  vi.mocked(listConversations).mockResolvedValue({ conversations: [OLD] });
  vi.mocked(createConversation).mockResolvedValue(conversation('n'.repeat(32), 'Nueva', 'b:8b'));
  vi.mocked(listAttachments).mockResolvedValue({ attachments: [] });
  vi.mocked(countConversationFeedback).mockResolvedValue(0);
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
      personality_id: 'builtin-general',
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

  it('a failure before the reply undoes the turn and gives the text back', async () => {
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

    await waitFor(() => expect(messageBox()).toHaveValue('uno'));
    expect(screen.queryByRole('article', { name: 'Tú' })).not.toBeInTheDocument();
    expect(notifyError).toHaveBeenCalledWith(failure);
  });

  it('a failure during the reply stays on the turn', async () => {
    const failure = new ApiError({
      kind: 'server',
      status: null,
      code: 'MODEL_UNAVAILABLE',
      message: 'Caído',
      requestId: 'r1',
    });
    vi.mocked(sendMessage).mockImplementationOnce(async (_id, _body, { onToken }) => {
      onToken('Empie');
      throw failure;
    });
    const { user } = await renderReady();

    await user.type(messageBox(), 'uno{Enter}');

    expect(await screen.findByText('No se pudo completar la respuesta.')).toBeInTheDocument();
    expect(messageBox()).toHaveValue('');
  });

  it('starts a new conversation', async () => {
    vi.mocked(sendMessage).mockResolvedValue({ model: 'b:8b', content: '' });
    const { user } = await renderReady();
    await user.type(messageBox(), 'hola{Enter}');
    expect(await screen.findByText('hola')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Nueva conversación' }));

    expect(await personalityTrigger()).toHaveTextContent('General');
    expect(messageBox()).toHaveFocus();
    expect(screen.queryByText('hola')).not.toBeInTheDocument();
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
  it('opens straight into the chat: no cards, General selected, composer focused', async () => {
    await renderReady();

    expect(await personalityTrigger()).toHaveTextContent('General');
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument();
    expect(screen.queryByText('Elige una personalidad')).not.toBeInTheDocument();
    await waitFor(() => expect(messageBox()).toHaveFocus());
  });

  it('changes the personality before the first message and then locks it', async () => {
    vi.mocked(sendMessage).mockResolvedValue({ model: 'a:7b', content: '' });
    const { user, select } = await renderReady();

    await choosePersonality(user, 'Pentester');
    expect(await personalityTrigger()).toHaveTextContent('Pentester');
    expect(select).toHaveValue('a:7b'); // the personality's preferred model
    await user.type(messageBox(), 'hola{Enter}');

    await waitFor(() =>
      expect(createConversation).toHaveBeenCalledWith({
        model: 'a:7b',
        personality_id: 'builtin-pentester',
      }),
    );
    expect(screen.queryByRole('combobox', { name: 'Personalidad' })).not.toBeInTheDocument();
    expect(lockedPersonality()).toHaveAccessibleName(
      'Personalidad: Pentester. La personalidad se fija al empezar la conversación',
    );
  });

  it('an opened conversation shows its personality locked', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      ...OLD,
      messages: [
        {
          id: 1,
          role: 'user',
          content: 'hola',
          status: 'done',
          created_at: OLD.created_at,
          attachments: [],
        },
      ],
    });
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Notas de un CTF' }));

    await waitFor(() => expect(lockedPersonality()).toHaveTextContent('Pentester'));
    expect(screen.queryByRole('combobox', { name: 'Personalidad' })).not.toBeInTheDocument();
  });

  it('a draft (a file attached, nothing sent) can still change its personality', async () => {
    vi.mocked(uploadAttachment).mockResolvedValue({
      id: 'f'.repeat(32),
      filename: 'a.txt',
      kind: 'text',
      mime: 'text/plain',
      size_bytes: 1,
      truncated: false,
      sent: false,
      created_at: OLD.created_at,
    });
    vi.mocked(setConversationPersonality).mockResolvedValue({
      ...conversation('n'.repeat(32), 'Nueva conversación'),
      personality: { id: 'builtin-pentester', name: 'Pentester', icon: 'crosshair' },
    });
    const { user } = await renderReady();
    await user.upload(
      screen.getByTestId('file-input'),
      new File(['x'], 'a.txt', { type: 'text/plain' }),
    );
    await screen.findByRole('button', { name: 'Quitar a.txt' });

    await choosePersonality(user, 'Pentester');

    expect(setConversationPersonality).toHaveBeenCalledWith('n'.repeat(32), 'builtin-pentester');
    expect(await personalityTrigger()).toHaveTextContent('Pentester');
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
      personality_id: 'builtin-general',
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

describe('ChatPage rate limits', () => {
  const CLOUD = {
    ...MODELS.models[0],
    name: 'groq/openai/gpt-oss-120b',
    remote: true,
    provider: 'groq',
  };
  const LOCAL = { ...MODELS.models[0], name: 'a:7b', remote: false, provider: 'ollama' };

  function rateLimited(retryAfter: number | null): ApiError {
    return new ApiError({
      kind: 'rate_limited',
      status: 429,
      code: 'MODEL_RATE_LIMITED',
      message: 'Límite de groq alcanzado.',
      requestId: 'r1',
      provider: 'groq',
      retryAfter,
    });
  }

  async function onCloudModel(defaultModel: string | null = 'a:7b') {
    vi.mocked(listModels).mockResolvedValue({
      models: [LOCAL, CLOUD],
      default_model: defaultModel,
    });
    const ready = await renderReady();
    await ready.user.selectOptions(ready.select, CLOUD.name);
    return ready;
  }

  it('says who hit the limit and when, keeps the text and does not toast', async () => {
    vi.mocked(sendMessage).mockRejectedValueOnce(rateLimited(12));
    const { user, select } = await onCloudModel();

    await user.type(messageBox(), 'resume esto{Enter}');

    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('Límite de groq alcanzado. Disponible en 12 s.');
    expect(messageBox()).toHaveValue('resume esto');
    expect(screen.queryByRole('article', { name: 'Tú' })).not.toBeInTheDocument();
    expect(notifyError).not.toHaveBeenCalled();
    expect(select).toHaveValue(CLOUD.name); // the model never changes on its own
  });

  it('without a retry time it just asks to wait', async () => {
    vi.mocked(sendMessage).mockRejectedValueOnce(rateLimited(null));
    const { user } = await onCloudModel();

    await user.type(messageBox(), 'hola{Enter}');

    expect(await screen.findByRole('status')).toHaveTextContent('Espera un poco.');
  });

  it('the button answers with the local default model, same text and same files', async () => {
    const file = {
      id: 'f'.repeat(32),
      filename: 'scan.nmap',
      kind: 'text' as const,
      mime: 'text/plain',
      size_bytes: 10,
      truncated: false,
      sent: false,
      created_at: OLD.created_at,
    };
    vi.mocked(uploadAttachment).mockResolvedValue(file);
    vi.mocked(listAttachments).mockResolvedValue({ attachments: [file] }); // pending again
    vi.mocked(sendMessage)
      .mockRejectedValueOnce(rateLimited(30))
      .mockResolvedValueOnce({ model: 'a:7b', content: 'ok' });
    const { user, select } = await onCloudModel();
    await user.upload(
      screen.getByTestId('file-input'),
      new File(['22/tcp open'], 'scan.nmap', { type: 'text/plain' }),
    );
    await screen.findByRole('button', { name: 'Quitar scan.nmap' });
    await user.type(messageBox(), 'analiza{Enter}');

    await user.click(await screen.findByRole('button', { name: 'Responder ahora con a:7b' }));

    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(2));
    const [, body] = vi.mocked(sendMessage).mock.calls[1];
    expect(body).toEqual({ content: 'analiza', model: 'a:7b', attachment_ids: [file.id] });
    expect(select).toHaveValue('a:7b');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(messageBox()).toHaveValue('');
  });

  it.each([
    ['there is no DEFAULT_MODEL', null],
    ['the default model is remote too', CLOUD.name],
  ])('no button when %s', async (_case, defaultModel) => {
    vi.mocked(sendMessage).mockRejectedValueOnce(rateLimited(5));
    const { user } = await onCloudModel(defaultModel);

    await user.type(messageBox(), 'hola{Enter}');

    await screen.findByRole('status');
    expect(screen.queryByRole('button', { name: /Responder ahora/ })).not.toBeInTheDocument();
  });

  it('a local provider (LM Studio) shows no cloud warnings', async () => {
    const lmstudio = {
      ...MODELS.models[0],
      name: 'lmstudio/qwen3.6-35b-a3b',
      remote: false,
      provider: 'lmstudio',
    };
    vi.mocked(listModels).mockResolvedValue({ models: [lmstudio], default_model: null });
    vi.mocked(uploadAttachment).mockResolvedValue({
      id: 'e'.repeat(32),
      filename: 'a.txt',
      kind: 'text',
      mime: 'text/plain',
      size_bytes: 1,
      truncated: false,
      sent: false,
      created_at: OLD.created_at,
    });
    const { user } = await renderReady();

    await user.upload(
      screen.getByTestId('file-input'),
      new File(['x'], 'a.txt', { type: 'text/plain' }),
    );

    await screen.findByRole('button', { name: 'Quitar a.txt' });
    expect(screen.queryByText(/saldrá de tu red/)).not.toBeInTheDocument();
  });
});

describe('ChatPage ratings', () => {
  function replyWith(result: { model: string; content: string; messageId?: number }) {
    vi.mocked(sendMessage).mockImplementation(
      async (_id, _body, { onToken }: StreamChatOptions) => {
        onToken(result.content);
        return result;
      },
    );
  }

  function replyArticle() {
    const replies = screen.getAllByRole('article', { name: 'Asistente' });
    return replies[replies.length - 1];
  }

  function savedFeedback(rating: 1 | -1) {
    return {
      message_id: 42,
      conversation_id: 'n'.repeat(32),
      rating,
      reasons: [],
      correction: null,
      question: 'hola',
      question_files: [],
      answer: 'Hola',
      model: 'b:8b',
      model_approximate: false,
      provider: 'ollama',
      personality: 'General',
      base_prompt_version: 'abcd1234',
      created_at: '',
      updated_at: '',
    };
  }

  it('a finished reply can be rated with the id the server gave it', async () => {
    replyWith({ model: 'b:8b', content: 'Hola', messageId: 42 });
    vi.mocked(rateMessage).mockResolvedValue(savedFeedback(1));
    const { user } = await renderReady();

    await user.type(messageBox(), 'hola{Enter}');
    await screen.findByText('Hola');
    const up = within(replyArticle()).getByRole('button', { name: 'Respuesta útil' });
    await user.click(up);

    expect(rateMessage).toHaveBeenCalledWith(42, { rating: 1, reasons: [], correction: null });
    await waitFor(() => expect(up).toHaveAttribute('aria-pressed', 'true'));
    await user.click(up);
    expect(unrateMessage).toHaveBeenCalledWith(42);
    await waitFor(() => expect(up).toHaveAttribute('aria-pressed', 'false'));
  });

  it('a reply without a server id has no rating buttons', async () => {
    replyWith({ model: 'b:8b', content: 'Hola' });
    const { user } = await renderReady();

    await user.type(messageBox(), 'hola{Enter}');
    await screen.findByText('Hola');

    expect(screen.queryByRole('button', { name: 'Respuesta útil' })).not.toBeInTheDocument();
  });

  it('undoes the rating and notifies when saving it fails', async () => {
    const failure = new ApiError({
      kind: 'server',
      status: 500,
      code: 'INTERNAL_ERROR',
      message: 'Error',
      requestId: 'r9',
    });
    replyWith({ model: 'b:8b', content: 'Hola', messageId: 42 });
    vi.mocked(rateMessage).mockRejectedValue(failure);
    const { user } = await renderReady();

    await user.type(messageBox(), 'hola{Enter}');
    await screen.findByText('Hola');
    const up = within(replyArticle()).getByRole('button', { name: 'Respuesta útil' });
    await user.click(up);

    await waitFor(() => expect(notifyError).toHaveBeenCalledWith(failure));
    expect(up).toHaveAttribute('aria-pressed', 'false');
  });

  it('an opened conversation shows its ratings, only on replies that can be rated', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      ...OLD,
      messages: [
        { id: 1, role: 'user', content: 'p', status: 'done', created_at: '', attachments: [] },
        {
          id: 2,
          role: 'assistant',
          content: 'mala',
          status: 'done',
          created_at: '',
          attachments: [],
          feedback: { rating: -1, reasons: ['incorrect'], correction: 'buena' },
        },
        { id: 3, role: 'user', content: 'q', status: 'done', created_at: '', attachments: [] },
        {
          id: 4,
          role: 'assistant',
          content: 'rota',
          status: 'error',
          created_at: '',
          attachments: [],
        },
      ],
    });
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Notas de un CTF' }));
    await screen.findByText('mala');

    const groups = screen.getAllByRole('group', { name: 'Valorar respuesta' });
    expect(groups).toHaveLength(1);
    expect(within(groups[0]).getByRole('button', { name: 'Respuesta mejorable' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await user.click(within(groups[0]).getByRole('button', { name: 'Respuesta mejorable' }));
    expect(await screen.findByLabelText('Inventado o incorrecto')).toBeChecked();
    // Shown as plain text in the form, never rendered.
    expect(screen.getByLabelText('¿Cuál sería la respuesta correcta?')).toHaveValue('buena');
  });

  it('a stopped reply gets its rating buttons once the server has saved it', async () => {
    vi.mocked(sendMessage).mockImplementation(
      (_id, _body, { signal, onToken }: StreamChatOptions) =>
        new Promise((_resolve, reject) => {
          onToken('parcial');
          signal?.addEventListener('abort', () => reject(abortError()));
        }),
    );
    vi.mocked(getConversation).mockResolvedValue({
      ...conversation('n'.repeat(32), 'Nueva', 'b:8b'),
      messages: [
        { id: 8, role: 'user', content: 'cuenta', status: 'done', created_at: '', attachments: [] },
        {
          id: 9,
          role: 'assistant',
          content: 'parcial',
          status: 'stopped',
          created_at: '',
          attachments: [],
        },
      ],
    });
    vi.mocked(rateMessage).mockResolvedValue(savedFeedback(1));
    const { user } = await renderReady();

    await user.type(messageBox(), 'cuenta{Enter}');
    await user.click(await screen.findByRole('button', { name: 'Detener' }));
    await screen.findByText('Respuesta detenida.');

    const up = await within(replyArticle()).findByRole('button', { name: 'Respuesta útil' });
    await user.click(up);
    expect(rateMessage).toHaveBeenCalledWith(9, { rating: 1, reasons: [], correction: null });
  });

  it('warns how many ratings go with a deleted conversation', async () => {
    vi.mocked(countConversationFeedback).mockResolvedValue(2);
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Borrar «Notas de un CTF»' }));
    const dialog = await screen.findByRole('alertdialog');

    expect(
      await within(dialog).findByText(/También se borrarán 2 valoraciones/),
    ).toBeInTheDocument();
    expect(countConversationFeedback).toHaveBeenCalledWith(OLD.id, expect.any(AbortSignal));
  });

  it('says nothing about ratings when the conversation has none', async () => {
    const { user } = await renderReady();

    await user.click(await screen.findByRole('button', { name: 'Borrar «Notas de un CTF»' }));
    const dialog = await screen.findByRole('alertdialog');
    await waitFor(() => expect(countConversationFeedback).toHaveBeenCalled());

    expect(within(dialog).queryByText(/valoraci/)).not.toBeInTheDocument();
  });
});
