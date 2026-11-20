import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  createOsintSource,
  deleteOsintSource,
  listOsintSources,
  replaceOsintSource,
  toggleOsintSource,
  type OsintSource,
} from '@/lib/api';
import { OsintSourcesPage } from './osint-sources-page';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listOsintSources: vi.fn(),
  createOsintSource: vi.fn(),
  replaceOsintSource: vi.fn(),
  toggleOsintSource: vi.fn(),
  deleteOsintSource: vi.fn(),
}));
vi.mock('sonner', async (importOriginal) => ({
  ...(await importOriginal<typeof import('sonner')>()),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function src(
  id: string,
  name: string,
  category: OsintSource['category'],
  builtin: boolean,
  extra: Partial<OsintSource> = {},
): OsintSource {
  return {
    id,
    name,
    url: `https://${name.toLowerCase().replace(/\s+/g, '')}.example`,
    category,
    description: `Desc ${name}`,
    requires_api_key: false,
    requires_payment: false,
    builtin,
    is_active: true,
    created_at: '',
    updated_at: '',
    ...extra,
  };
}

const HIBP = src('osint-hibp', 'Have I Been Pwned', 'breach', true);
const SHERLOCK = src('osint-sherlock', 'Sherlock', 'username', true);
const MINE = src('c'.repeat(32), 'Mi fuente', 'domain', false);

function row(name: string) {
  const cell = screen.getByText(name);
  const tr = cell.closest('tr');
  if (!tr) throw new Error(`no row for ${name}`);
  return tr;
}

async function renderPage() {
  const user = userEvent.setup();
  render(<OsintSourcesPage />);
  await screen.findByText('Mi fuente');
  return user;
}

beforeEach(() => {
  vi.mocked(listOsintSources).mockResolvedValue({ sources: [HIBP, SHERLOCK, MINE] });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('OsintSourcesManager', () => {
  it('filters the list by category', async () => {
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Usuarios' }));

    expect(screen.getByRole('button', { name: 'Usuarios' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByText('Sherlock')).toBeInTheDocument();
    expect(screen.queryByText('Have I Been Pwned')).not.toBeInTheDocument();
    expect(screen.queryByText('Mi fuente')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Todas' }));
    expect(screen.getByText('Have I Been Pwned')).toBeInTheDocument();
  });

  it('built-ins show no edit or delete buttons', async () => {
    await renderPage();
    const builtin = row('Have I Been Pwned');

    expect(within(builtin).getByText('Incorporada')).toBeInTheDocument();
    expect(within(builtin).queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument();
    expect(within(builtin).queryByRole('button', { name: /Eliminar/ })).not.toBeInTheDocument();
  });

  it('toggles is_active on a built-in', async () => {
    vi.mocked(toggleOsintSource).mockResolvedValue({ ...HIBP, is_active: false });
    const user = await renderPage();

    await user.click(screen.getByRole('switch', { name: 'Desactivar «Have I Been Pwned»' }));

    await waitFor(() => expect(toggleOsintSource).toHaveBeenCalledWith('osint-hibp'));
    expect(
      await screen.findByRole('switch', { name: 'Activar «Have I Been Pwned»' }),
    ).not.toBeChecked();
    expect(within(row('Have I Been Pwned')).getByText('Inactiva')).toBeInTheDocument();
  });

  it('edits a custom source with PUT', async () => {
    vi.mocked(replaceOsintSource).mockResolvedValue({ ...MINE, name: 'Renombrada' });
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Editar «Mi fuente»' }));
    const dialog = await screen.findByRole('dialog');
    const name = within(dialog).getByLabelText('Nombre');
    await user.clear(name);
    await user.type(name, 'Renombrada');
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(replaceOsintSource).toHaveBeenCalledWith(
        MINE.id,
        expect.objectContaining({ name: 'Renombrada', is_active: true, category: 'domain' }),
      ),
    );
    expect(await screen.findByText('Renombrada')).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith('Fuente guardada.');
  });

  it('deletes a custom source after confirming', async () => {
    vi.mocked(deleteOsintSource).mockResolvedValue(undefined);
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Eliminar «Mi fuente»' }));
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Eliminar' }),
    );

    await waitFor(() => expect(deleteOsintSource).toHaveBeenCalledWith(MINE.id));
    await waitFor(() => expect(screen.queryByText('Mi fuente')).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith('«Mi fuente» eliminada.');
  });

  it('shows server validation errors inside the form', async () => {
    vi.mocked(createOsintSource).mockRejectedValue(
      new ApiError({
        kind: 'validation',
        status: 422,
        code: 'VALIDATION_ERROR',
        message: 'body.url: La URL solo puede tener caracteres ASCII imprimibles',
        requestId: 'r',
      }),
    );
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Añadir' }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Nombre'), 'Falsa');
    const url = within(dialog).getByLabelText('URL');
    await user.clear(url);
    await user.type(url, 'https://xn--pple-43d.com');
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('ASCII');
  });

  it('never renders unsafe URLs as links', async () => {
    vi.mocked(listOsintSources).mockResolvedValue({
      sources: [src('d'.repeat(32), 'Rara', 'domain', false, { url: 'javascript:alert(1)' })],
    });
    render(<OsintSourcesPage />);

    const rara = await screen.findByText('Rara');
    expect(rara.closest('tr')?.querySelector('a')).toBeNull();
  });

  it('opens safe links in a new tab without opener', async () => {
    await renderPage();

    const link = within(row('Have I Been Pwned')).getByRole('link');
    expect(link).toHaveAttribute('href', 'https://haveibeenpwned.example');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
