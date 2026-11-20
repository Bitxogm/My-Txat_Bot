import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LoginPage } from './login-page';

describe('LoginPage quick-login card', () => {
  it('fills username and password without submitting', async () => {
    const onLogin = vi.fn();
    const user = userEvent.setup();
    render(<LoginPage onLogin={onLogin} devLogin={{ username: 'void', password: 'dev-pass' }} />);

    await user.click(screen.getByRole('button', { name: /Acceso rápido · void/ }));

    expect(screen.getByLabelText('Usuario')).toHaveValue('void');
    expect(screen.getByLabelText('Contraseña')).toHaveValue('dev-pass');
    expect(onLogin).not.toHaveBeenCalled();
  });

  it('is not shown without dev credentials', () => {
    render(<LoginPage onLogin={vi.fn()} devLogin={null} />);

    expect(screen.queryByRole('button', { name: /Acceso rápido/ })).not.toBeInTheDocument();
  });
});
