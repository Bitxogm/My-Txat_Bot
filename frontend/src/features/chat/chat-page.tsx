import { useEffect, useRef, useState } from 'react';
import { LogOutIcon, MenuIcon, PanelLeftCloseIcon, PanelLeftOpenIcon } from 'lucide-react';
import { ThemeToggle } from '@/components/theme-toggle';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet';
import {
  ConversationSidebar,
  type SettingsPage,
} from '@/features/conversations/conversation-sidebar';
import { useConversations } from '@/features/conversations/use-conversations';
import { CorrectionsPage } from '@/features/feedback/corrections-page';
import { OsintSourcesPage } from '@/features/osint-sources/osint-sources-page';
import { PersonalitiesPage } from '@/features/personalities/personalities-page';
import { PersonalitySelect } from '@/features/personalities/personality-select';
import {
  DEFAULT_PERSONALITY_ID,
  usePersonalities,
} from '@/features/personalities/use-personalities';
import { setConversationPersonality, type Personality } from '@/lib/api';
import { notifyError } from '@/lib/notify-error';
import {
  isDesktop,
  isSidebarCollapsed,
  isSidebarShortcut,
  setSidebarCollapsed,
  useSidebarCollapsed,
} from '@/lib/sidebar';
import { cn } from '@/lib/utils';
import { Composer } from './composer';
import { RateLimitNotice, type RateLimit } from './rate-limit-notice';
import { useAttachments } from './use-attachments';
import { MessageList } from './message-list';
import { ModelSelect } from './model-select';
import { RATE_LIMITED, useChat } from './use-chat';
import { useModels } from './use-models';

interface ChatPageProps {
  username: string;
  onLogout: () => void;
}

export function ChatPage({ username, onLogout }: ChatPageProps) {
  const { models, selected, select, status, reload, defaultModel } = useModels();
  const conversations = useConversations();
  const chat = useChat({ onActivity: conversations.refresh });
  const personalities = usePersonalities();
  const attachments = useAttachments();
  const [draft, setDraft] = useState('');
  const [rateLimit, setRateLimit] = useState<RateLimit | null>(null);
  // Mobile: the sidebar is an overlay panel, closed on every load. Desktop: it can be folded
  // away, and that choice is remembered (lib/sidebar.ts).
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { collapsed } = useSidebarCollapsed();
  const sidebarToggle = useRef<HTMLButtonElement>(null);
  const asideRef = useRef<HTMLElement>(null);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!isSidebarShortcut(event) || !isDesktop()) return;
      // Not under an open dialog (delete confirmation, the 👎 form...).
      if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"]'))
        return;
      event.preventDefault();
      foldSidebar(!isSidebarCollapsed());
    }
    // Capture phase: it works with the focus in the message box too.
    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true });
  }, []);

  function foldSidebar(fold: boolean) {
    // Focus inside the sidebar would be lost when it goes: move it to the button.
    if (fold && asideRef.current?.contains(document.activeElement)) sidebarToggle.current?.focus();
    setSidebarCollapsed(fold);
  }
  const [page, setPage] = useState<SettingsPage | null>(null);
  const [personalityId, setPersonalityId] = useState(DEFAULT_PERSONALITY_ID);
  // Bumped by "Nueva conversación" so the composer takes the focus again.
  const [newChats, setNewChats] = useState(0);
  // A reply to scroll to once its conversation is open (from the corrections page).
  const [highlight, setHighlight] = useState<number | null>(null);

  async function choosePersonality(personality: Personality) {
    const previous = personalityId;
    setPersonalityId(personality.id);
    // A draft already exists (a file was attached): change it on the server too (ADR-022).
    if (chat.conversationId) {
      try {
        const updated = await setConversationPersonality(chat.conversationId, personality.id);
        chat.setPersonality(updated.personality);
      } catch (error) {
        notifyError(error);
        setPersonalityId(previous);
        return;
      }
    }
    // The personality's preferred model, if it's available here.
    if (personality.default_model && models.some((m) => m.name === personality.default_model)) {
      select(personality.default_model);
    }
  }

  function openPage(next: SettingsPage) {
    setSidebarOpen(false);
    setPage(next);
  }

  async function openConversation(id: string, messageId: number | null = null) {
    setSidebarOpen(false);
    setPage(null);
    setRateLimit(null);
    setHighlight(messageId);
    const detail = await chat.open(id);
    // Files uploaded earlier and never sent come back to the composer.
    void attachments.load(detail ? id : null);
    if (detail && models.some((m) => m.name === detail.model)) select(detail.model);
  }

  function startNew() {
    setSidebarOpen(false);
    setPage(null);
    setHighlight(null);
    setRateLimit(null);
    setPersonalityId(DEFAULT_PERSONALITY_ID);
    setNewChats((n) => n + 1);
    attachments.clear();
    chat.startNew();
  }

  async function deleteConversation(id: string) {
    if (id === chat.conversationId) {
      attachments.clear();
      chat.startNew();
    }
    await conversations.remove(id);
  }

  async function attach(files: File[]) {
    // Files belong to a conversation: a new chat is created on the first attachment.
    const id = await chat.ensureConversation(selected, personalityId);
    if (id) await attachments.add(id, files);
  }

  function removeFile(key: string) {
    if (chat.conversationId) void attachments.remove(chat.conversationId, key);
  }

  async function sendWithFiles(content: string, model: string = selected) {
    const files = attachments.ready;
    if (files.length > 0) attachments.clear();
    setRateLimit(null);
    setDraft('');
    const { conversationId, failed } = await chat.send(content, model, personalityId, files);
    // Resync: whatever the server did not take (e.g. the send failed) shows up again.
    if (files.length > 0) void attachments.load(conversationId);
    if (!failed) return;
    // The turn was undone (ADR-019): the text goes back as it was, nothing to retype.
    setDraft(failed.text);
    if (failed.error.code === RATE_LIMITED) {
      const seconds = failed.error.retryAfter;
      setRateLimit({
        provider: failed.error.provider ?? model.split('/')[0],
        until: seconds === null ? null : Date.now() + seconds * 1000,
      });
    }
  }

  // The local fallback: DEFAULT_MODEL, only if it is available here and doesn't leave the machine.
  const localFallback =
    defaultModel && models.some((m) => m.name === defaultModel && !m.remote) ? defaultModel : null;

  function answerWithLocal() {
    if (!localFallback || !draft.trim()) return;
    select(localFallback); // only because the user pressed the button
    void sendWithFiles(draft, localFallback);
  }

  const selectedModel = models.find((m) => m.name === selected);
  const isRemoteModel = selectedModel?.remote ?? false;
  const hasPendingImages = attachments.files.some((f) => f.attachment?.kind === 'image');
  const blockReason =
    hasPendingImages && selectedModel && !selectedModel.vision
      ? `${selectedModel.name} no ve imágenes. Elige un modelo que las vea o quita las imágenes.`
      : null;
  const sentImages = chat.messages.some((m) => m.attachments.some((a) => a.kind === 'image'));
  // Earlier images are re-sent to a vision model on every turn (the newest few, ADR-016).
  const notice =
    isRemoteModel && selectedModel?.vision && sentImages
      ? 'Modelo en la nube: las imágenes recientes de esta conversación también saldrán de tu red.'
      : null;

  // The personality is fixed by the first message (ADR-013, ADR-022): an opened conversation is
  // locked, a new chat or a draft (files attached, nothing sent) is not.
  const personalityLocked =
    chat.messages.some((m) => m.role === 'user') ||
    (chat.isLoading && chat.conversationId !== null);

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
      {!collapsed && (
        <aside
          id="conversations-sidebar"
          ref={asideRef}
          className="bg-sidebar hidden w-64 shrink-0 flex-col border-r md:flex"
        >
          <div className="border-b px-4 py-3">
            <h1 className="font-heading text-base font-semibold">Txat_bot</h1>
          </div>
          {sidebar}
        </aside>
      )}
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
            <Button
              ref={sidebarToggle}
              variant="ghost"
              size="icon-sm"
              className="hidden md:inline-flex"
              onClick={() => foldSidebar(!collapsed)}
              aria-expanded={!collapsed}
              aria-controls={collapsed ? undefined : 'conversations-sidebar'}
              aria-label={collapsed ? 'Mostrar conversaciones' : 'Ocultar conversaciones'}
              title={`${collapsed ? 'Mostrar' : 'Ocultar'} conversaciones (Ctrl+B)`}
            >
              {collapsed ? <PanelLeftOpenIcon /> : <PanelLeftCloseIcon />}
            </Button>
            <span
              className={cn(
                'font-heading text-base font-semibold',
                collapsed ? 'md:inline' : 'md:hidden',
              )}
            >
              Txat_bot
            </span>
          </div>
          <div className="flex items-center gap-1">
            {page === null && (
              <PersonalitySelect
                personalities={personalities.personalities}
                value={personalityId}
                onChange={(p) => void choosePersonality(p)}
                locked={personalityLocked}
                fixed={chat.personality}
                disabled={chat.isStreaming}
              />
            )}
            <ModelSelect
              models={models}
              value={selected}
              onChange={select}
              status={status}
              onReload={reload}
              disabled={chat.isStreaming}
            />
            <ThemeToggle />
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
        ) : page === 'osint' ? (
          <OsintSourcesPage />
        ) : page === 'corrections' ? (
          <CorrectionsPage
            models={models.map((m) => m.name)}
            personalities={personalities.personalities.map((p) => p.name)}
            onOpenConversation={(id, messageId) => void openConversation(id, messageId)}
          />
        ) : (
          <>
            <MessageList
              messages={chat.messages}
              loading={chat.isLoading}
              conversationId={chat.conversationId}
              localModel={selectedModel ? !selectedModel.remote : false}
              onRate={chat.rate}
              highlightId={highlight}
            />
            <Composer
              focusKey={`${chat.conversationId ?? 'new'}:${newChats}:${page ?? 'chat'}`}
              onSend={(content) => void sendWithFiles(content)}
              draft={draft}
              onDraftChange={setDraft}
              banner={
                rateLimit && (
                  <RateLimitNotice
                    key={rateLimit.until ?? 'unknown'}
                    limit={rateLimit}
                    localModel={localFallback}
                    onUseLocal={answerWithLocal}
                    disabled={chat.isStreaming || attachments.isUploading}
                  />
                )
              }
              onStop={chat.stop}
              isStreaming={chat.isStreaming}
              disabled={!selected || chat.isLoading}
              files={attachments.files}
              isUploading={attachments.isUploading}
              onAttach={(files) => void attach(files)}
              onRemoveFile={removeFile}
              filesNote={
                isRemoteModel
                  ? 'Modelo en la nube: el contenido de estos ficheros saldrá de tu red.'
                  : null
              }
              blockReason={blockReason}
              notice={notice}
            />
          </>
        )}
      </div>
    </div>
  );
}
