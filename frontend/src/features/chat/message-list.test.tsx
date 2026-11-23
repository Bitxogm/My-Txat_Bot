import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MessageList } from './message-list';
import { MODEL_LOADING_DELAY_MS, MODEL_LOADING_NOTE } from './pending-reply';
import type { UiMessage } from './use-chat';

let nextId = 0;
function assistant(content: string, status: UiMessage['status']): UiMessage {
  return { id: `a${nextId++}`, role: 'assistant', content, status, attachments: [] };
}

vi.mock('./markdown/markdown', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./markdown/markdown')>();
  return {
    ...actual,
    Markdown: (props: { content: string }) => {
      if (props.content.startsWith('BOOM')) throw new Error('Maximum call stack size exceeded');
      return <actual.Markdown {...props} />;
    },
  };
});

describe('MessageList', () => {
  it('falls back to plain text for a reply that breaks the Markdown renderer', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    render(
      <MessageList
        messages={[assistant('BOOM > > > anidado', 'done'), assistant('**ok**', 'done')]}
      />,
    );

    expect(await screen.findByText('BOOM > > > anidado')).toBeInTheDocument();
    // The Markdown chunk is lazy-loaded; under a full parallel run that can take >1 s.
    expect(await screen.findByText('ok', undefined, { timeout: 5000 })).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it('flags a finished reply with no text instead of showing an empty bubble', () => {
    render(<MessageList messages={[assistant('', 'done')]} />);

    expect(screen.getByText('El modelo no devolvió ninguna respuesta.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Generando')).not.toBeInTheDocument();
  });

  it('shows the typing indicator while streaming', () => {
    render(<MessageList messages={[assistant('', 'streaming')]} />);

    expect(screen.getByLabelText('Generando')).toBeInTheDocument();
  });

  it('shows the error note for failed empty turns', () => {
    render(<MessageList messages={[assistant('', 'error')]} />);

    expect(screen.getByText('No se pudo completar la respuesta.')).toBeInTheDocument();
  });

  it('keeps normal replies untouched', () => {
    render(<MessageList messages={[assistant('Hola', 'done')]} />);

    expect(screen.getByText('Hola')).toBeInTheDocument();
    expect(screen.queryByText(/no devolvió/)).not.toBeInTheDocument();
  });

  describe('before the first token', () => {
    it('says a local model is loading when the first token takes over 3 s', () => {
      vi.useFakeTimers();
      try {
        render(<MessageList messages={[assistant('', 'streaming')]} localModel />);
        expect(screen.getByLabelText('Generando')).toBeInTheDocument();
        expect(screen.queryByText(MODEL_LOADING_NOTE)).not.toBeInTheDocument();

        act(() => vi.advanceTimersByTime(MODEL_LOADING_DELAY_MS));

        expect(screen.getByRole('status')).toHaveTextContent(MODEL_LOADING_NOTE);
        expect(screen.queryByLabelText('Generando')).not.toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });

    it('keeps only the typing indicator for a remote model', () => {
      vi.useFakeTimers();
      try {
        render(<MessageList messages={[assistant('', 'streaming')]} />);

        act(() => vi.advanceTimersByTime(MODEL_LOADING_DELAY_MS * 2));

        expect(screen.getByLabelText('Generando')).toBeInTheDocument();
        expect(screen.queryByText(MODEL_LOADING_NOTE)).not.toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });

    it('drops the note once the first token arrives', () => {
      vi.useFakeTimers();
      try {
        const { rerender } = render(
          <MessageList messages={[assistant('', 'streaming')]} localModel />,
        );
        act(() => vi.advanceTimersByTime(MODEL_LOADING_DELAY_MS));
        const reply: UiMessage = { ...assistant('', 'streaming'), content: 'Hola' };

        rerender(<MessageList messages={[reply]} localModel />);

        expect(screen.queryByText(MODEL_LOADING_NOTE)).not.toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });
  });
});
