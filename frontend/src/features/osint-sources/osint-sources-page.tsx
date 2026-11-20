import { OsintSourcesManager } from './osint-sources-manager';
import { useOsintSources } from './use-osint-sources';

/** Loads the catalog only when the page is opened. */
export function OsintSourcesPage() {
  const store = useOsintSources();
  return <OsintSourcesManager store={store} />;
}
