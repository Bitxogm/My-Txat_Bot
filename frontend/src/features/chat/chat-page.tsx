import { useState } from 'react';
import { LogOutIcon, MenuIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import { ConversationSidebar } from '@/features/conversations/conversation-sidebar';
import { useConversations } from '@/features/conversations/use-conversations';
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
  const conversations = useConversations();
  const chat = useChat({ onActivity: conversations.refresh });
  const [sidebarOpen, setSidebarOpen] = useState(false);

  async function openConversation(id: string) {
    setSidebarOpen(false);
    const detail = await chat.open(id);
    if (detail && models.some((m) => m.name === detail.model)) select(detail.model);
  }

  function startNew() {
    setSidebarOpen(false);
    chat.startNew();
  }

  async function deleteConversation(id: string) {
    if (id === chat.conversationId) chat.startNew();
    await conversations.remove(id);
  }

  const sidebar = (
    <ConversationSidebar
      conversations={conversations.conversations}
      loading={conversations.loading}
      activeId={chat.conversationId}
      onSelect={(id) => void openConversation(id)}
      onNew={startNew}
      onDelete={(id) => void deleteConversation(id)}
    />
  );

  return (
    <div className="flex h-svh">
      <aside className="bg-sidebar hidden w-64 shrink-0 flex-col border-r md:flex">
        <div className="border-b px-4 py-3">
          <h1 className="font-heading text-base font-semibold">Txat_bot</h1>
        </div>
        {sidebar}
      </aside>
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-72 gap-0 p-0">
          <SheetTitle className="border-b px-4 py-3 text-base">Txat_bot</SheetTitle>
          {sidebar}
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-2 border-b px-2 py-2 md:px-4">
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              className="md:hidden"
              onClick={() => setSidebarOpen(true)}
              aria-label="Abrir conversaciones"
            >
              <MenuIcon />
            </Button>
            <span className="font-heading text-base font-semibold md:hidden">Txat_bot</span>
          </div>
          <div className="flex items-center gap-1">
            <ModelSelect
              models={models}
              value={selected}
              onChange={select}
              status={status}
              onReload={reload}
              disabled={chat.isStreaming}
            />
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => {
                // Stop any reply in progress before the session is closed.
                chat.stop();
                onLogout();
              }}
              aria-label={`Cerrar sesión (${username})`}
              title={`Cerrar sesión (${username})`}
            >
              <LogOutIcon />
            </Button>
          </div>
        </header>
        <MessageList messages={chat.messages} loading={chat.isLoading} />
        <Composer
          onSend={(content) => void chat.send(content, selected)}
          onStop={chat.stop}
          isStreaming={chat.isStreaming}
          disabled={!selected || chat.isLoading}
        />
      </div>
    </div>
  );
}
