import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  deletePersonality,
  duplicatePersonality,
  listPersonalities,
  updatePersonality,
  type Personality,
} from '@/lib/api';
import { PersonalitiesPage } from './personalities-page';
import { usePersonalities } from './use-personalities';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  listPersonalities: vi.fn(),
  updatePersonality: vi.fn(),
  deletePersonality: vi.fn(),
  duplicatePersonality: vi.fn(),
  createPersonality: vi.fn(),
}));
vi.mock('sonner', async (importOriginal) => ({
  ...(await importOriginal<typeof import('sonner')>()),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function personality(id: string, name: string, builtin: boolean): Personality {
  return {
    id,
    name,
    icon: 'bot',
    description: '',
    system_prompt: `Prompt de ${name}`,
    temperature: 0.5,
    top_p: null,
    num_ctx: null,
    default_model: null,
    builtin,
    created_at: '',
    updated_at: '',
  };
}

const MENTOR = personality('builtin-mentor-ctf', 'Mentor CTF', true);
const MINE = personality('a'.repeat(32), 'Mi copia', false);

function Harness() {
  const store = usePersonalities();
  return <PersonalitiesPage store={store} models={[]} />;
}

async function renderPage() {
  const user = userEvent.setup();
  render(<Harness />);
  await screen.findByRole('listitem', { name: 'Mi copia' });
  return user;
}

beforeEach(() => {
  vi.mocked(listPersonalities).mockResolvedValue({ personalities: [MENTOR, MINE] });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('PersonalitiesPage', () => {
  it('built-ins can be viewed and duplicated but not edited or deleted', async () => {
    await renderPage();
    const builtin = screen.getByRole('listitem', { name: 'Mentor CTF' });

    expect(within(builtin).getByText('Incorporada')).toBeInTheDocument();
    expect(within(builtin).getByRole('button', { name: 'Ver «Mentor CTF»' })).toBeInTheDocument();
    expect(
      within(builtin).getByRole('button', { name: 'Duplicar «Mentor CTF»' }),
    ).toBeInTheDocument();
    expect(within(builtin).queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument();
    expect(within(builtin).queryByRole('button', { name: /Borrar/ })).not.toBeInTheDocument();
  });

  it('opens built-ins read-only', async () => {
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Ver «Mentor CTF»' }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText('Prompt de la personalidad')).toBeDisabled();
    expect(within(dialog).queryByRole('button', { name: 'Guardar' })).not.toBeInTheDocument();
  });

  it('duplicates a built-in', async () => {
    vi.mocked(duplicatePersonality).mockResolvedValue({
      ...MENTOR,
      id: 'b'.repeat(32),
      name: 'Mentor CTF (copia)',
      builtin: false,
    });
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Duplicar «Mentor CTF»' }));

    await waitFor(() => expect(duplicatePersonality).toHaveBeenCalledWith('builtin-mentor-ctf'));
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Mentor CTF (copia)'));
  });

  it('edits a copy with PATCH', async () => {
    vi.mocked(updatePersonality).mockResolvedValue({ ...MINE, name: 'Renombrada' });
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Editar «Mi copia»' }));
    const dialog = await screen.findByRole('dialog');
    const name = within(dialog).getByLabelText('Nombre');
    await user.clear(name);
    await user.type(name, 'Renombrada');
    await user.clear(within(dialog).getByLabelText('Temperatura (0-2)'));
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(updatePersonality).toHaveBeenCalledWith(
        MINE.id,
        expect.objectContaining({ name: 'Renombrada', temperature: null }),
      ),
    );
    expect(toast.success).toHaveBeenCalledWith('Personalidad guardada.');
  });

  it('validates parameter ranges before saving', async () => {
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Editar «Mi copia»' }));
    const dialog = await screen.findByRole('dialog');
    const temperature = within(dialog).getByLabelText('Temperatura (0-2)');
    await user.clear(temperature);
    await user.type(temperature, '3');
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('0 a 2');
    expect(updatePersonality).not.toHaveBeenCalled();
  });

  it('deletes a copy after confirming', async () => {
    vi.mocked(deletePersonality).mockResolvedValue(undefined);
    const user = await renderPage();

    await user.click(screen.getByRole('button', { name: 'Borrar «Mi copia»' }));
    const confirm = await screen.findByRole('alertdialog');
    expect(within(confirm).getByText(/guardan su propia copia/)).toBeInTheDocument();
    await user.click(within(confirm).getByRole('button', { name: 'Borrar' }));

    await waitFor(() => expect(deletePersonality).toHaveBeenCalledWith(MINE.id));
    await waitFor(() =>
      expect(screen.queryByRole('listitem', { name: 'Mi copia' })).not.toBeInTheDocument(),
    );
  });
});
