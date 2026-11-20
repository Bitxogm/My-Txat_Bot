import { useState } from 'react';
import { MessageSquarePlusIcon, RadarIcon, Trash2Icon, VenetianMaskIcon } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import type { Conversation } from '@/lib/api';
import { cn } from '@/lib/utils';

interface ConversationSidebarProps {
  conversations: Conversation[];
  loading: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  /** Settings pages linked at the bottom; `activePage` highlights the open one. */
  onOpenPage: (page: SettingsPage) => void;
  activePage: SettingsPage | null;
}

export type SettingsPage = 'personalities' | 'osint';

const SETTINGS_LINKS: { page: SettingsPage; label: string; icon: typeof VenetianMaskIcon }[] = [
  { page: 'personalities', label: 'Personalidades', icon: VenetianMaskIcon },
  { page: 'osint', label: 'Fuentes OSINT', icon: RadarIcon },
];

export function ConversationSidebar({
  conversations,
  loading,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onOpenPage,
  activePage,
}: ConversationSidebarProps) {
  const [pendingDelete, setPendingDelete] = useState<Conversation | null>(null);

  return (
    <nav aria-label="Conversaciones" className="flex h-full min-h-0 flex-col">
      <div className="p-2">
        <Button
          variant="outline"
          className="w-full justify-start"
          onClick={onNew}
          aria-label="Nueva conversación"
        >
          <MessageSquarePlusIcon />
          Nueva conversación
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {loading ? (
          <p className="text-muted-foreground px-2 py-1 text-sm">Cargando…</p>
        ) : conversations.length === 0 ? (
          <p className="text-muted-foreground px-2 py-1 text-sm">Aún no hay conversaciones.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((conversation) => {
              const active = conversation.id === activeId;
              return (
                <li key={conversation.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'hover:bg-muted w-full truncate rounded-md py-2 pr-9 pl-2 text-left text-sm',
                      active && 'bg-muted font-medium',
                    )}
                    title={conversation.title}
                  >
                    {conversation.title}
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    className="absolute top-1/2 right-1 -translate-y-1/2 group-focus-within:opacity-100 group-hover:opacity-100 md:opacity-0"
                    onClick={() => setPendingDelete(conversation)}
                    aria-label={`Borrar «${conversation.title}»`}
                  >
                    <Trash2Icon />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <div className="border-t p-2">
        <p className="text-muted-foreground px-2 pb-1 text-xs font-medium">Configuración</p>
        {SETTINGS_LINKS.map(({ page, label, icon: Icon }) => (
          <button
            key={page}
            type="button"
            onClick={() => onOpenPage(page)}
            aria-current={activePage === page ? 'page' : undefined}
            className={cn(
              'hover:bg-muted flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm',
              activePage === page && 'bg-muted font-medium',
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Borrar la conversación?</AlertDialogTitle>
            <AlertDialogDescription>
              Se borrará «{pendingDelete?.title}» con todos sus mensajes. No se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (pendingDelete) onDelete(pendingDelete.id);
                setPendingDelete(null);
              }}
            >
              Borrar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </nav>
  );
}
