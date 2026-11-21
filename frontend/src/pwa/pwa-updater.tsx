import { useEffect } from 'react';
import { toast } from 'sonner';
import { useRegisterSW } from 'virtual:pwa-register/react';

const UPDATE_TOAST_ID = 'pwa-update';

/**
 * Registers the service worker (production builds; HTTPS or localhost only) and, when a new
 * version is waiting, asks before reloading: an update never interrupts a reply in progress.
 */
export function PwaUpdater() {
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  useEffect(() => {
    if (!needRefresh) return;
    toast('Nueva versión disponible', {
      id: UPDATE_TOAST_ID,
      duration: Infinity,
      action: { label: 'Recargar', onClick: () => void updateServiceWorker(true) },
    });
  }, [needRefresh, updateServiceWorker]);

  return null;
}
