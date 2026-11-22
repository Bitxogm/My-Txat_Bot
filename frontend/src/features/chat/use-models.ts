import { useCallback, useEffect, useState } from 'react';
import { isAbortError, listModels, type ModelInfo } from '@/lib/api';
import { notifyError } from '@/lib/notify-error';

export type ModelsStatus = 'loading' | 'ready' | 'error';

export interface UseModels {
  models: ModelInfo[];
  selected: string;
  select: (name: string) => void;
  status: ModelsStatus;
  reload: () => void;
  /** DEFAULT_MODEL of the backend, if it is in the list. */
  defaultModel: string | null;
}

function pickInitial(models: ModelInfo[], defaultModel: string | null): string {
  if (defaultModel && models.some((m) => m.name === defaultModel)) return defaultModel;
  return models[0]?.name ?? '';
}

export function useModels(): UseModels {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selected, setSelected] = useState('');
  const [status, setStatus] = useState<ModelsStatus>('loading');
  const [attempt, setAttempt] = useState(0);
  const [defaultModel, setDefaultModel] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listModels(controller.signal).then(
      (response) => {
        setModels(response.models);
        setDefaultModel(
          response.models.some((m) => m.name === response.default_model)
            ? response.default_model
            : null,
        );
        setSelected((current) =>
          response.models.some((m) => m.name === current)
            ? current
            : pickInitial(response.models, response.default_model),
        );
        setStatus('ready');
      },
      (error: unknown) => {
        if (isAbortError(error)) return;
        notifyError(error);
        setStatus('error');
      },
    );
    return () => controller.abort();
  }, [attempt]);

  const reload = useCallback(() => {
    setStatus('loading');
    setAttempt((n) => n + 1);
  }, []);

  return { models, selected, select: setSelected, status, reload, defaultModel };
}
