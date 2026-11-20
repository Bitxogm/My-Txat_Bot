import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MessageList } from './message-list';
import type { UiMessage } from './use-chat';

let nextId = 0;
function assistant(content: string, status: UiMessage['status']): UiMessage {
  return { id: `a${nextId++}`, role: 'assistant', content, status };
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
    expect(await screen.findByText('ok')).toBeInTheDocument();
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
});
