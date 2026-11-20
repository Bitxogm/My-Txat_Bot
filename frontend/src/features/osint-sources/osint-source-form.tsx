import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { OsintCategory, OsintSource, OsintSourceInput } from '@/lib/api';
import { OSINT_CATEGORIES } from './categories';
import type { SaveResult } from './use-osint-sources';

interface OsintSourceFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Custom source to edit; undefined creates a new one. */
  source?: OsintSource;
  onSave: (input: OsintSourceInput) => Promise<SaveResult>;
}

export function OsintSourceForm({ open, onOpenChange, source, onSave }: OsintSourceFormProps) {
  const [name, setName] = useState(source?.name ?? '');
  const [url, setUrl] = useState(source?.url ?? 'https://');
  const [category, setCategory] = useState<OsintCategory>(source?.category ?? 'breach');
  const [description, setDescription] = useState(source?.description ?? '');
  const [requiresApiKey, setRequiresApiKey] = useState(source?.requires_api_key ?? false);
  const [requiresPayment, setRequiresPayment] = useState(source?.requires_payment ?? false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    if (!name.trim()) return setError('El nombre es obligatorio.');
    if (!/^https?:\/\/\S+$/.test(url.trim()))
      return setError('La URL debe empezar por http:// o https://.');
    setError(null);
    setSaving(true);
    // The server does the real validation (ASCII, public domain, no credentials…).
    const result = await onSave({
      name: name.trim(),
      url: url.trim(),
      category,
      description: description.trim(),
      requires_api_key: requiresApiKey,
      requires_payment: requiresPayment,
      is_active: source?.is_active ?? true,
    });
    setSaving(false);
    if (result.ok) onOpenChange(false);
    else if (result.message) setError(result.message);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{source ? 'Editar fuente' : 'Nueva fuente OSINT'}</DialogTitle>
          <DialogDescription>
            Las fuentes activas se pasan al Auditor de Huella Digital como datos de referencia.
          </DialogDescription>
        </DialogHeader>
        <form id="osint-source-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="o-name">Nombre</Label>
            <Input
              id="o-name"
              value={name}
              maxLength={60}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="o-url">URL</Label>
            <Input
              id="o-url"
              type="url"
              inputMode="url"
              value={url}
              maxLength={300}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="o-category">Categoría</Label>
            <NativeSelect
              id="o-category"
              value={category}
              onChange={(e) => setCategory(e.target.value as OsintCategory)}
            >
              {OSINT_CATEGORIES.map((c) => (
                <NativeSelectOption key={c.value} value={c.value}>
                  {c.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="o-description">Descripción</Label>
            <Input
              id="o-description"
              value={description}
              maxLength={200}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap gap-6">
            <div className="flex items-center gap-2">
              <Checkbox
                id="o-api"
                checked={requiresApiKey}
                onCheckedChange={(v) => setRequiresApiKey(v === true)}
              />
              <Label htmlFor="o-api">Requiere API key</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="o-paid"
                checked={requiresPayment}
                onCheckedChange={(v) => setRequiresPayment(v === true)}
              />
              <Label htmlFor="o-paid">De pago</Label>
            </div>
          </div>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button type="submit" form="osint-source-form" disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
