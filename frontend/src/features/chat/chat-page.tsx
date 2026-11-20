import { LogOutIcon, PlusIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Composer } from './composer';
import { MessageList } from './message-list';
import { ModelSelect } from './model-select';
import { useChat } from './use-chat';
import { useModels } from './use-models';

interface ChatPageProps {
  username: string;
  onLogout: () => void;
}

export function ChatPage({ username, onLogout }: ChatPageProps) {
  const { models, selected, select, status, reload } = useModels();
  const { messages, isStreaming, send, stop, reset } = useChat();

  return (
    <div className="flex h-svh flex-col">
      <header className="flex items-center justify-between gap-2 border-b px-4 py-2">
        <h1 className="font-heading text-base font-semibold">Txat_bot</h1>
        <div className="flex items-center gap-1">
          <ModelSelect
            models={models}
            value={selected}
            onChange={select}
            status={status}
            onReload={reload}
            disabled={isStreaming}
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={reset}
            disabled={messages.length === 0}
            aria-label="Nueva conversación"
          >
            <PlusIcon />
            <span className="hidden sm:inline">Nueva</span>
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              // Stop any reply in progress before the session is closed.
              stop();
              onLogout();
            }}
            aria-label={`Cerrar sesión (${username})`}
            title={`Cerrar sesión (${username})`}
          >
            <LogOutIcon />
          </Button>
        </div>
      </header>
      <MessageList messages={messages} />
      <Composer
        onSend={(content) => void send(content, selected)}
        onStop={stop}
        isStreaming={isStreaming}
        disabled={!selected}
      />
    </div>
  );
}
