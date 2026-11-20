import { useState } from 'react';
import { LogOutIcon, MenuIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import {
  ConversationSidebar,
  type SettingsPage,
} from '@/features/conversations/conversation-sidebar';
import { useConversations } from '@/features/conversations/use-conversations';
import { PersonalitiesPage } from '@/features/personalities/personalities-page';
import { PersonalityBadge } from '@/features/personalities/personality-badge';
import { PersonalityPicker } from '@/features/personalities/personality-picker';
import {
  DEFAULT_PERSONALITY_ID,
  usePersonalities,
} from '@/features/personalities/use-personalities';
import type { Personality } from '@/lib/api';
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
  const personalities = usePersonalities();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [page, setPage] = useState<SettingsPage | null>(null);
  const [personalityId, setPersonalityId] = useState(DEFAULT_PERSONALITY_ID);

  function choosePersonality(personality: Personality) {
    setPersonalityId(personality.id);
    // The personality's preferred model, if it's available here.
    if (personality.default_model && models.some((m) => m.name === personality.default_model)) {
      select(personality.default_model);
    }
  }

  function openPage(next: SettingsPage) {
    setSidebarOpen(false);
    setPage(next);
  }

  async function openConversation(id: string) {
    setSidebarOpen(false);
    setPage(null);
    const detail = await chat.open(id);
    if (detail && models.some((m) => m.name === detail.model)) select(detail.model);
  }

  function startNew() {
    setSidebarOpen(false);
    setPage(null);
    setPersonalityId(DEFAULT_PERSONALITY_ID);
    chat.startNew();
  }

  async function deleteConversation(id: string) {
    if (id === chat.conversationId) chat.startNew();
    await conversations.remove(id);
  }

  // A brand-new chat (nothing sent yet) shows the personality picker instead of messages.
  const isNewChat =
    !chat.conversationId && chat.messages.length === 0 && personalities.personalities.length > 0;

  const sidebar = (
    <ConversationSidebar
      conversations={conversations.conversations}
      loading={conversations.loading}
      activeId={chat.conversationId}
      onSelect={(id) => void openConversation(id)}
      onNew={startNew}
      onDelete={(id) => void deleteConversation(id)}
      onOpenPage={openPage}
      activePage={page}
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
            {page === null && chat.conversationId && (
              <span className="hidden sm:flex">
                <PersonalityBadge personality={chat.personality} />
              </span>
            )}
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
        {page === 'personalities' ? (
          <PersonalitiesPage store={personalities} models={models} />
        ) : (
          <>
            {isNewChat ? (
              <div className="flex-1 overflow-y-auto">
                <div className="mx-auto w-full max-w-3xl px-4 py-6">
                  <PersonalityPicker
                    personalities={personalities.personalities}
                    value={personalityId}
                    onChange={choosePersonality}
                    models={models}
                  />
                </div>
              </div>
            ) : (
              <MessageList messages={chat.messages} loading={chat.isLoading} />
            )}
            <Composer
              onSend={(content) => void chat.send(content, selected, personalityId)}
              onStop={chat.stop}
              isStreaming={chat.isStreaming}
              disabled={!selected || chat.isLoading}
            />
          </>
        )}
      </div>
    </div>
  );
}
