import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MessageList } from './message-list';
import type { UiMessage } from './use-chat';

function assistant(content: string, status: UiMessage['status']): UiMessage {
  return { id: 'a', role: 'assistant', content, status };
}

describe('MessageList', () => {
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
