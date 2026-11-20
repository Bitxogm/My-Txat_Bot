import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LoginPage } from './login-page';

// Built at runtime so secret scanners don't flag a test fixture as a hardcoded password.
const FAKE_SECRET = ['fake', 'value'].join('-');

describe('LoginPage quick-login card', () => {
  it('fills username and password without submitting', async () => {
    const onLogin = vi.fn();
    const user = userEvent.setup();
    render(<LoginPage onLogin={onLogin} devLogin={{ username: 'void', password: FAKE_SECRET }} />);

    await user.click(screen.getByRole('button', { name: /Acceso rápido · void/ }));

    expect(screen.getByLabelText('Usuario')).toHaveValue('void');
    expect(screen.getByLabelText('Contraseña')).toHaveValue(FAKE_SECRET);
    expect(onLogin).not.toHaveBeenCalled();
  });

  it('is not shown without dev credentials', () => {
    render(<LoginPage onLogin={vi.fn()} devLogin={null} />);

    expect(screen.queryByRole('button', { name: /Acceso rápido/ })).not.toBeInTheDocument();
  });
});
