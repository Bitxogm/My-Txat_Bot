import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
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
import { Textarea } from '@/components/ui/textarea';
import type { ModelInfo, Personality, PersonalityInput } from '@/lib/api';
import { PERSONALITY_ICONS } from './personality-icon';

// Same limits as the backend (domain/personality.py); the server validates again.
const LIMITS = {
  name: 60,
  description: 200,
  systemPrompt: 8000,
  temperature: [0, 2],
  topP: [0, 1],
  numCtx: [512, 16384],
} as const;

interface PersonalityFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Personality to view or edit; undefined creates a new one. */
  personality?: Personality;
  readOnly?: boolean;
  models: ModelInfo[];
  onSave: (input: PersonalityInput) => Promise<boolean>;
}

function toText(value: number | null): string {
  return value === null ? '' : String(value);
}

function parseNumber(text: string): number | null {
  const trimmed = text.trim().replace(',', '.');
  return trimmed === '' ? null : Number(trimmed);
}

export function PersonalityForm({
  open,
  onOpenChange,
  personality,
  readOnly = false,
  models,
  onSave,
}: PersonalityFormProps) {
  const [name, setName] = useState(personality?.name ?? '');
  const [icon, setIcon] = useState(personality?.icon ?? 'bot');
  const [description, setDescription] = useState(personality?.description ?? '');
  const [systemPrompt, setSystemPrompt] = useState(personality?.system_prompt ?? '');
  const [temperature, setTemperature] = useState(toText(personality?.temperature ?? null));
  const [topP, setTopP] = useState(toText(personality?.top_p ?? null));
  const [numCtx, setNumCtx] = useState(toText(personality?.num_ctx ?? null));
  const [defaultModel, setDefaultModel] = useState(personality?.default_model ?? '');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function validate(): PersonalityInput | string {
    const t = parseNumber(temperature);
    const p = parseNumber(topP);
    const c = parseNumber(numCtx);
    if (!name.trim()) return 'El nombre es obligatorio.';
    if (!systemPrompt.trim()) return 'El prompt de la personalidad es obligatorio.';
    if (t !== null && !(t >= LIMITS.temperature[0] && t <= LIMITS.temperature[1]))
      return 'La temperatura va de 0 a 2.';
    if (p !== null && !(p > LIMITS.topP[0] && p <= LIMITS.topP[1]))
      return 'top_p debe ser mayor que 0 y como máximo 1.';
    if (c !== null && !(Number.isInteger(c) && c >= LIMITS.numCtx[0] && c <= LIMITS.numCtx[1]))
      return 'El contexto (num_ctx) va de 512 a 16384, sin decimales.';
    return {
      name: name.trim(),
      icon,
      description: description.trim(),
      system_prompt: systemPrompt.trim(),
      temperature: t,
      top_p: p,
      num_ctx: c,
      default_model: defaultModel || null,
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly || saving) return;
    const result = validate();
    if (typeof result === 'string') {
      setError(result);
      return;
    }
    setError(null);
    setSaving(true);
    const ok = await onSave(result);
    setSaving(false);
    if (ok) onOpenChange(false);
  }

  const title = readOnly
    ? personality?.name
    : personality
      ? 'Editar personalidad'
      : 'Nueva personalidad';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {readOnly
              ? 'Personalidad incorporada: solo lectura. Duplícala para personalizarla.'
              : 'La capa base con los límites éticos se añade siempre delante y no se puede editar.'}
          </DialogDescription>
        </DialogHeader>
        <form id="personality-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
          <fieldset disabled={readOnly} className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
              <div className="flex flex-col gap-2">
                <Label htmlFor="p-name">Nombre</Label>
                <Input
                  id="p-name"
                  value={name}
                  maxLength={LIMITS.name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="p-icon">Icono</Label>
                <NativeSelect id="p-icon" value={icon} onChange={(e) => setIcon(e.target.value)}>
                  {Object.keys(PERSONALITY_ICONS).map((key) => (
                    <NativeSelectOption key={key} value={key}>
                      {key}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="p-description">Descripción</Label>
              <Input
                id="p-description"
                value={description}
                maxLength={LIMITS.description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="p-prompt">Prompt de la personalidad</Label>
              <Textarea
                id="p-prompt"
                value={systemPrompt}
                maxLength={LIMITS.systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                className="min-h-48 font-mono text-xs"
              />
              <span className="text-muted-foreground self-end text-xs">
                {systemPrompt.length} / {LIMITS.systemPrompt}
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="flex flex-col gap-2">
                <Label htmlFor="p-temperature">Temperatura (0-2)</Label>
                <Input
                  id="p-temperature"
                  inputMode="decimal"
                  placeholder="del modelo"
                  value={temperature}
                  onChange={(e) => setTemperature(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="p-top-p">top_p (0-1)</Label>
                <Input
                  id="p-top-p"
                  inputMode="decimal"
                  placeholder="del modelo"
                  value={topP}
                  onChange={(e) => setTopP(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="p-num-ctx">Contexto (num_ctx)</Label>
                <Input
                  id="p-num-ctx"
                  inputMode="numeric"
                  placeholder="del modelo"
                  value={numCtx}
                  onChange={(e) => setNumCtx(e.target.value)}
                />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="p-model">Modelo por defecto</Label>
              <NativeSelect
                id="p-model"
                value={defaultModel}
                onChange={(e) => setDefaultModel(e.target.value)}
              >
                <NativeSelectOption value="">El que esté elegido en el chat</NativeSelectOption>
                {defaultModel && !models.some((m) => m.name === defaultModel) && (
                  <NativeSelectOption value={defaultModel}>
                    {defaultModel} (no disponible)
                  </NativeSelectOption>
                )}
                {models.map((m) => (
                  <NativeSelectOption key={m.name} value={m.name}>
                    {m.remote ? `${m.name} (nube)` : m.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
          </fieldset>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {readOnly ? 'Cerrar' : 'Cancelar'}
          </Button>
          {!readOnly && (
            <Button type="submit" form="personality-form" disabled={saving}>
              {saving ? 'Guardando…' : 'Guardar'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
