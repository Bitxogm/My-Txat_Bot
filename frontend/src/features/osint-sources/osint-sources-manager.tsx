import { useState } from 'react';
import { PencilIcon, PlusIcon, Trash2Icon } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { safeUrl } from '@/features/chat/markdown/safe-url';
import type { OsintCategory, OsintSource, OsintSourceInput } from '@/lib/api';
import { cn } from '@/lib/utils';
import { categoryLabel, OSINT_CATEGORIES } from './categories';
import { OsintSourceForm } from './osint-source-form';
import type { UseOsintSources } from './use-osint-sources';

type FormState = { mode: 'closed' } | { mode: 'create' } | { mode: 'edit'; source: OsintSource };

/** Host as the browser normalises it (IDN shown as punycode, so look-alikes stand out). */
function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function SourceLink({ url }: { url: string }) {
  const href = safeUrl(url);
  if (!href || !/^https?:/.test(href)) return <span>{hostOf(url)}</span>;
  return (
    <a
      href={href}
      title={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-2"
    >
      {hostOf(url)}
    </a>
  );
}

const yesNo = (value: boolean) => (value ? 'Sí' : 'No');

export function OsintSourcesManager({ store }: { store: UseOsintSources }) {
  const [filter, setFilter] = useState<OsintCategory | null>(null);
  const [form, setForm] = useState<FormState>({ mode: 'closed' });
  const [pendingDelete, setPendingDelete] = useState<OsintSource | null>(null);

  const visible = filter ? store.sources.filter((s) => s.category === filter) : store.sources;
  const activeCount = store.sources.filter((s) => s.is_active).length;

  async function save(input: OsintSourceInput) {
    const id = form.mode === 'edit' ? form.source.id : undefined;
    const result = await store.save(input, id);
    if (result.ok) toast.success(id ? 'Fuente guardada.' : 'Fuente añadida.');
    return result;
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    const target = pendingDelete;
    setPendingDelete(null);
    if (await store.remove(target.id)) toast.success(`«${target.name}» eliminada.`);
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-heading text-lg font-semibold">Fuentes OSINT</h2>
            <p className="text-muted-foreground text-sm">
              Catálogo que usa el Auditor de Huella Digital para recomendar herramientas sobre tus
              propios datos. Las incorporadas solo se activan o desactivan. Activas: {activeCount}{' '}
              de {store.sources.length}.
            </p>
          </div>
          <Button onClick={() => setForm({ mode: 'create' })}>
            <PlusIcon />
            Añadir
          </Button>
        </div>

        <div role="group" aria-label="Filtrar por categoría" className="flex flex-wrap gap-1.5">
          {[{ value: null, label: 'Todas' }, ...OSINT_CATEGORIES].map((c) => (
            <button
              key={c.value ?? 'all'}
              type="button"
              aria-pressed={filter === c.value}
              onClick={() => setFilter(c.value)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs transition-colors',
                filter === c.value
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'hover:bg-muted',
              )}
            >
              {c.label}
            </button>
          ))}
        </div>

        {store.loading ? (
          <p className="text-muted-foreground text-sm">Cargando…</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full min-w-[760px] text-left text-sm">
              <caption className="sr-only">Fuentes OSINT</caption>
              <thead className="bg-muted/50 text-muted-foreground text-xs">
                <tr>
                  <th className="px-3 py-2 font-medium">Nombre</th>
                  <th className="px-3 py-2 font-medium">URL</th>
                  <th className="px-3 py-2 font-medium">Categoría</th>
                  <th className="px-3 py-2 font-medium">Requiere API</th>
                  <th className="px-3 py-2 font-medium">Requiere pago</th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((s) => (
                  <tr key={s.id} className={cn('border-t', !s.is_active && 'opacity-60')}>
                    <td className="px-3 py-2 align-top">
                      <div className="flex flex-col gap-1">
                        <span className="flex items-center gap-2">
                          <span className="font-medium">{s.name}</span>
                          <Badge variant={s.builtin ? 'secondary' : 'outline'}>
                            {s.builtin ? 'Incorporada' : 'Propia'}
                          </Badge>
                        </span>
                        <span className="text-muted-foreground text-xs">{s.description}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <SourceLink url={s.url} />
                    </td>
                    <td className="px-3 py-2 align-top">{categoryLabel(s.category)}</td>
                    <td className="px-3 py-2 align-top">{yesNo(s.requires_api_key)}</td>
                    <td className="px-3 py-2 align-top">{yesNo(s.requires_payment)}</td>
                    <td className="px-3 py-2 align-top">
                      <span className="flex items-center gap-2">
                        <Switch
                          checked={s.is_active}
                          onCheckedChange={() => void store.toggle(s.id)}
                          aria-label={`${s.is_active ? 'Desactivar' : 'Activar'} «${s.name}»`}
                        />
                        <span className="text-xs">{s.is_active ? 'Activa' : 'Inactiva'}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right align-top">
                      {!s.builtin && (
                        <span className="inline-flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setForm({ mode: 'edit', source: s })}
                            aria-label={`Editar «${s.name}»`}
                          >
                            <PencilIcon />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setPendingDelete(s)}
                            aria-label={`Eliminar «${s.name}»`}
                          >
                            <Trash2Icon />
                          </Button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {form.mode !== 'closed' && (
        <OsintSourceForm
          key={form.mode === 'edit' ? form.source.id : 'new'}
          open
          onOpenChange={(open) => {
            if (!open) setForm({ mode: 'closed' });
          }}
          source={form.mode === 'edit' ? form.source : undefined}
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
            <AlertDialogTitle>¿Eliminar la fuente?</AlertDialogTitle>
            <AlertDialogDescription>
              Se eliminará «{pendingDelete?.name}» del catálogo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void confirmDelete()}>
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
