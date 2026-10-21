import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, api } from '../api/client';
import { getToken } from '../lib/tokenStore';
import { SignInPage } from './SignInPage';

vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>();
  return { ...actual, api: { ...actual.api, getDashboard: vi.fn() } };
});

const getDashboard = vi.mocked(api.getDashboard);

function renderSignIn() {
  render(
    <MemoryRouter initialEntries={['/sign-in']}>
      <Routes>
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/dashboard" element={<h1>Dashboard page</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getDashboard.mockReset();
});

describe('SignInPage', () => {
  it('validates the token against the dashboard, stores it and continues', async () => {
    getDashboard.mockResolvedValue({ counts: {} as never, stale_tickets: [] });
    renderSignIn();
    await userEvent.type(screen.getByLabelText(/staff token/i), '  fictional-staff-token-1234 ');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Dashboard page')).toBeInTheDocument();
    expect(getDashboard).toHaveBeenCalledWith('fictional-staff-token-1234');
    expect(getToken()).toBe('fictional-staff-token-1234');
  });

  it('shows "Invalid or expired token" and clears the field on 401', async () => {
    getDashboard.mockRejectedValue(new ApiError(401, 'unauthorized', 'Missing or invalid staff token.'));
    renderSignIn();
    const input = screen.getByLabelText(/staff token/i);
    await userEvent.type(input, 'wrong-token-fictional-99');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid or expired token');
    expect(input).toHaveValue('');
    expect(getToken()).toBeNull();
  });

  it('asks for a token instead of calling the API when empty', async () => {
    renderSignIn();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Paste the staff token.');
    expect(getDashboard).not.toHaveBeenCalled();
  });
});
