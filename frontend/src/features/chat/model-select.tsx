import { RotateCwIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  NativeSelect,
  NativeSelectOptGroup,
  NativeSelectOption,
} from '@/components/ui/native-select';
import type { ModelInfo } from '@/lib/api';
import type { ModelsStatus } from './use-models';

interface ModelSelectProps {
  models: ModelInfo[];
  value: string;
  onChange: (name: string) => void;
  status: ModelsStatus;
  onReload: () => void;
  disabled?: boolean;
}

const GROUPS = [
  { label: 'Local', remote: false },
  { label: 'Nube (sale de tu red)', remote: true },
] as const;

function describe(model: ModelInfo): string {
  const details = [model.parameter_size, model.quantization].filter(Boolean).join(' · ');
  return details ? `${model.name} (${details})` : model.name;
}

export function ModelSelect({
  models,
  value,
  onChange,
  status,
  onReload,
  disabled,
}: ModelSelectProps) {
  const placeholder =
    status === 'loading'
      ? 'Cargando modelos…'
      : status === 'error'
        ? 'Modelos no disponibles'
        : 'No hay modelos';

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="model-select" className="sr-only">
        Modelo
      </label>
      <NativeSelect
        id="model-select"
        size="sm"
        className="max-w-64"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || models.length === 0}
      >
        {models.length === 0 ? (
          <NativeSelectOption value="">{placeholder}</NativeSelectOption>
        ) : (
          GROUPS.map(({ label, remote }) => {
            const group = models.filter((m) => m.remote === remote);
            return group.length === 0 ? null : (
              <NativeSelectOptGroup key={label} label={label}>
                {group.map((model) => (
                  <NativeSelectOption key={model.name} value={model.name}>
                    {describe(model)}
                  </NativeSelectOption>
                ))}
              </NativeSelectOptGroup>
            );
          })
        )}
      </NativeSelect>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onReload}
        disabled={status === 'loading'}
        aria-label="Recargar modelos"
        title="Recargar modelos"
      >
        <RotateCwIcon />
      </Button>
    </div>
  );
}
