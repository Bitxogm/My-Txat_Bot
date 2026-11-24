import { useId, useState, type FormEvent } from 'react';
import { DownloadIcon, MessageSquareIcon, Trash2Icon } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { Feedback, FeedbackFilters, FeedbackReason } from '@/lib/api';
import { FeedbackButtons } from './feedback-buttons';
import { REASON_LABELS, REASONS } from './reasons';
import { useCorrections, type UseCorrections } from './use-corrections';

export interface CorrectionsPageProps {
  /** Model and personality names offered in the filters. */
  models: string[];
  personalities: string[];
  onOpenConversation: (conversationId: string, messageId: number) => void;
}

/** Loads the ratings only when the page is opened. */
export function CorrectionsPage(props: CorrectionsPageProps) {
  const store = useCorrections();
  return <CorrectionsView store={store} {...props} />;
}

const DATE = new Intl.DateTimeFormat('es-ES', { dateStyle: 'medium', timeStyle: 'short' });

/** The filter form keeps strings; empty means "any". */
interface FilterDraft {
  rating: '' | '1' | '-1';
  model: string;
  personality: string;
  reason: '' | FeedbackReason;
  from: string;
  to: string;
}

const EMPTY_DRAFT: FilterDraft = {
  rating: '',
  model: '',
  personality: '',
  reason: '',
  from: '',
  to: '',
};

function toFilters(draft: FilterDraft): FeedbackFilters {
  return {
    rating: draft.rating === '' ? undefined : draft.rating === '1' ? 1 : -1,
    model: draft.model || undefined,
    personality: draft.personality || undefined,
    reason: draft.reason || undefined,
    from: draft.from || undefined,
    to: draft.to || undefined,
  };
}

export function CorrectionsView({
  store,
  models,
  personalities,
  onOpenConversation,
}: CorrectionsPageProps & { store: UseCorrections }) {
  const id = useId();
  const [draft, setDraft] = useState<FilterDraft>(EMPTY_DRAFT);
  const [pendingDelete, setPendingDelete] = useState<Feedback | null>(null);
  const { items, total, loading } = store;

  function set<K extends keyof FilterDraft>(key: K, value: FilterDraft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function apply(event: FormEvent) {
    event.preventDefault();
    store.setFilters(toFilters(draft));
  }

  function clear() {
    setDraft(EMPTY_DRAFT);
    store.setFilters({});
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h1 className="text-lg font-semibold">Correcciones</h1>
            <p className="text-muted-foreground text-sm">
              Las valoraciones de las respuestas. El modelo no las ve todavía: se usarán para el
              RAG, la batería de evaluación y el entrenamiento.
            </p>
          </div>
          <Button variant="outline" onClick={() => void store.download()}>
            <DownloadIcon />
            Exportar JSONL
          </Button>
        </div>

        <form
          aria-label="Filtros"
          onSubmit={apply}
          className="grid grid-cols-2 gap-3 rounded-lg border p-3 sm:grid-cols-3 lg:grid-cols-6"
        >
          <div className="grid gap-1">
            <Label htmlFor={`${id}-rating`}>Valoración</Label>
            <NativeSelect
              id={`${id}-rating`}
              value={draft.rating}
              onChange={(e) => set('rating', e.target.value as FilterDraft['rating'])}
            >
              <NativeSelectOption value="">Todas</NativeSelectOption>
              <NativeSelectOption value="1">👍 Útil</NativeSelectOption>
              <NativeSelectOption value="-1">👎 Mejorable</NativeSelectOption>
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${id}-reason`}>Motivo</Label>
            <NativeSelect
              id={`${id}-reason`}
              value={draft.reason}
              onChange={(e) => set('reason', e.target.value as FilterDraft['reason'])}
            >
              <NativeSelectOption value="">Todos</NativeSelectOption>
              {REASONS.map((reason) => (
                <NativeSelectOption key={reason} value={reason}>
                  {REASON_LABELS[reason]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${id}-model`}>Modelo</Label>
            <NativeSelect
              id={`${id}-model`}
              value={draft.model}
              onChange={(e) => set('model', e.target.value)}
            >
              <NativeSelectOption value="">Todos</NativeSelectOption>
              {models.map((model) => (
                <NativeSelectOption key={model} value={model}>
                  {model}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${id}-personality`}>Personalidad</Label>
            <NativeSelect
              id={`${id}-personality`}
              value={draft.personality}
              onChange={(e) => set('personality', e.target.value)}
            >
              <NativeSelectOption value="">Todas</NativeSelectOption>
              {personalities.map((name) => (
                <NativeSelectOption key={name} value={name}>
                  {name}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${id}-from`}>Desde</Label>
            <Input
              id={`${id}-from`}
              type="date"
              value={draft.from}
              onChange={(e) => set('from', e.target.value)}
            />
          </div>
          <div className="grid gap-1">
            <Label htmlFor={`${id}-to`}>Hasta</Label>
            <Input
              id={`${id}-to`}
              type="date"
              value={draft.to}
              onChange={(e) => set('to', e.target.value)}
            />
          </div>
          <div className="col-span-full flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={clear}>
              Limpiar
            </Button>
            <Button type="submit">Filtrar</Button>
          </div>
        </form>

        <p role="status" className="text-muted-foreground text-sm">
          {loading && items.length === 0
            ? 'Cargando valoraciones…'
            : total === 1
              ? '1 valoración'
              : `${total} valoraciones`}
        </p>

        {!loading && items.length === 0 ? (
          <p className="text-muted-foreground py-12 text-center text-sm">
            No hay valoraciones con estos filtros. Valora las respuestas con 👍 o 👎 en el chat.
          </p>
        ) : (
          <ul aria-label="Valoraciones" className="flex flex-col gap-3">
            {items.map((item) => (
              <li key={item.message_id}>
                <CorrectionCard
                  item={item}
                  onRate={(feedback) => store.rate(item.message_id, feedback)}
                  onDelete={() => setPendingDelete(item)}
                  onOpen={() => onOpenConversation(item.conversation_id, item.message_id)}
                />
              </li>
            ))}
          </ul>
        )}

        {items.length < total && (
          <Button
            variant="outline"
            className="self-center"
            disabled={loading}
            onClick={() => void store.loadMore()}
          >
            Cargar más
          </Button>
        )}
      </div>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Borrar la valoración?</AlertDialogTitle>
            <AlertDialogDescription>
              Se borrará la valoración con sus motivos y su corrección. La respuesta sigue en su
              conversación.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (pendingDelete) void store.rate(pendingDelete.message_id, null);
                setPendingDelete(null);
              }}
            >
              Borrar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** Plain text only: questions, answers and corrections are never rendered as HTML. */
function TextColumn({ title, text, empty }: { title: string; text: string; empty: string }) {
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-1">
      <h3 className="text-muted-foreground text-xs font-medium uppercase">{title}</h3>
      <div className="bg-muted/50 max-h-64 overflow-y-auto rounded-md p-2 text-sm break-words whitespace-pre-wrap">
        {text || <span className="text-muted-foreground italic">{empty}</span>}
      </div>
    </section>
  );
}

function CorrectionCard({
  item,
  onRate,
  onDelete,
  onOpen,
}: {
  item: Feedback;
  onRate: (feedback: Parameters<UseCorrections['rate']>[1]) => Promise<boolean>;
  onDelete: () => void;
  onOpen: () => void;
}) {
  const question = item.question_files.length
    ? `${item.question}\n\n[Ficheros: ${item.question_files.join(', ')}]`
    : item.question;
  return (
    <article
      aria-label={`Valoración del ${DATE.format(new Date(item.created_at))}`}
      className="flex flex-col gap-3 rounded-lg border p-3"
    >
      <header className="flex flex-wrap items-center gap-2 text-xs">
        <FeedbackButtons
          feedback={{ rating: item.rating, reasons: item.reasons, correction: item.correction }}
          onRate={onRate}
        />
        {item.reasons.map((reason) => (
          <Badge key={reason} variant="secondary">
            {REASON_LABELS[reason]}
          </Badge>
        ))}
        <span className="text-muted-foreground">
          {item.model}
          {item.model_approximate && ' (aproximado)'}
          {item.personality && ` · ${item.personality}`} · capa base{' '}
          {item.base_prompt_version ?? 'desconocido'} · {DATE.format(new Date(item.created_at))}
        </span>
        <span className="ml-auto flex gap-1">
          <Button variant="ghost" size="sm" onClick={onOpen}>
            <MessageSquareIcon />
            Ir a la conversación
          </Button>
          <Button variant="ghost" size="sm" aria-label="Borrar valoración" onClick={onDelete}>
            <Trash2Icon />
          </Button>
        </span>
      </header>
      <div className="grid gap-3 md:grid-cols-3">
        <TextColumn title="Pregunta" text={question} empty="Sin pregunta" />
        <TextColumn title="Respuesta" text={item.answer} empty="Sin texto" />
        <TextColumn title="Corrección" text={item.correction ?? ''} empty="Sin corrección" />
      </div>
    </article>
  );
}
