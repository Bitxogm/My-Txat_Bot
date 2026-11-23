import { useState } from 'react';
import { CopyIcon, EyeIcon, PencilIcon, PlusIcon, Trash2Icon } from 'lucide-react';
import { toast } from 'sonner';
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
import type { ModelInfo, Personality, PersonalityInput } from '@/lib/api';
import { PersonalityCards } from './personality-cards';
import { PersonalityForm } from './personality-form';
import type { UsePersonalities } from './use-personalities';

type FormState =
  { mode: 'closed' } | { mode: 'create' } | { mode: 'edit' | 'view'; personality: Personality };

function params(p: Personality): string {
  const parts = [
    p.temperature !== null && `temp ${p.temperature}`,
    p.top_p !== null && `top_p ${p.top_p}`,
    p.num_ctx !== null && `ctx ${p.num_ctx}`,
    p.default_model && `modelo ${p.default_model}`,
  ].filter(Boolean);
  return parts.length ? parts.join(' · ') : 'Parámetros del modelo';
}

interface PersonalitiesPageProps {
  store: UsePersonalities;
  models: ModelInfo[];
}

export function PersonalitiesPage({ store, models }: PersonalitiesPageProps) {
  const [form, setForm] = useState<FormState>({ mode: 'closed' });
  const [pendingDelete, setPendingDelete] = useState<Personality | null>(null);

  async function save(input: PersonalityInput): Promise<boolean> {
    const id = form.mode === 'edit' ? form.personality.id : undefined;
    const saved = await store.save(input, id);
    if (saved) toast.success(id ? 'Personalidad guardada.' : 'Personalidad creada.');
    return saved !== null;
  }

  async function duplicate(personality: Personality) {
    const copy = await store.duplicate(personality.id);
    if (copy) toast.success(`Creada «${copy.name}». Ya puedes editarla.`);
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    if (await store.remove(target.id)) toast.success(`«${target.name}» borrada.`);
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-heading text-lg font-semibold">Personalidades</h2>
            <p className="text-muted-foreground text-sm">
              Definen el tono y el método del asistente. La capa base con los límites éticos se
              añade siempre y no se puede editar. Las incorporadas no se editan: duplícalas.
            </p>
          </div>
          <Button onClick={() => setForm({ mode: 'create' })}>
            <PlusIcon />
            Nueva
          </Button>
        </div>

        {store.loading ? (
          <p className="text-muted-foreground text-sm">Cargando…</p>
        ) : (
          <PersonalityCards
            personalities={store.personalities}
            details={(p) => (
              <p className="text-muted-foreground font-mono text-[11px]">{params(p)}</p>
            )}
            actions={(p) => (
              <>
                {p.builtin ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setForm({ mode: 'view', personality: p })}
                    aria-label={`Ver «${p.name}»`}
                  >
                    <EyeIcon />
                    Ver
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setForm({ mode: 'edit', personality: p })}
                    aria-label={`Editar «${p.name}»`}
                  >
                    <PencilIcon />
                    Editar
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => void duplicate(p)}
                  aria-label={`Duplicar «${p.name}»`}
                >
                  <CopyIcon />
                  Duplicar
                </Button>
                {!p.builtin && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setPendingDelete(p)}
                    aria-label={`Borrar «${p.name}»`}
                  >
                    <Trash2Icon />
                  </Button>
                )}
              </>
            )}
          />
        )}
      </div>

      {form.mode !== 'closed' && (
        <PersonalityForm
          key={form.mode === 'create' ? 'new' : `${form.mode}-${form.personality.id}`}
          open
          onOpenChange={(open) => {
            if (!open) setForm({ mode: 'closed' });
          }}
          personality={form.mode === 'create' ? undefined : form.personality}
          readOnly={form.mode === 'view'}
          models={models}
          onSave={save}
        />
      )}

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Borrar la personalidad?</AlertDialogTitle>
            <AlertDialogDescription>
              Se borrará «{pendingDelete?.name}». Las conversaciones que ya la usan la conservan,
              porque guardan su propia copia.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void confirmDelete()}>
              Borrar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
