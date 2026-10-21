import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';

import { ApiError, EXPIRED_TOKEN_MESSAGE, api } from '../api/client';
import { TextField } from '../components/fields';
import { Banner } from '../components/ui';
import { SHOP_NAME } from '../config';
import { describeError } from '../lib/errors';
import { setToken } from '../lib/tokenStore';

interface SignInState {
  message?: string;
  from?: string;
}

export function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as SignInState;
  const [token, setTokenInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const candidate = token.trim();
    if (!candidate) {
      setError('Paste the staff token.');
      return;
    }
    setChecking(true);
    setError(null);
    try {
      await api.getDashboard(candidate); // validates the token
      setToken(candidate);
      navigate(state.from ?? '/dashboard', { replace: true });
    } catch (err) {
      setChecking(false);
      if (err instanceof ApiError && err.status === 401) {
        setTokenInput(''); // a rejected token is useless; don't keep it in the field
        setError(EXPIRED_TOKEN_MESSAGE);
      } else if (err instanceof ApiError) setError(describeError(err));
      else setError('Something went wrong. Please try again.');
    }
  }

  const notice = error ?? state.message ?? null;
  const isError = error !== null || state.message === EXPIRED_TOKEN_MESSAGE;

  return (
    <main id="main" className="signin">
      <form className="card signin__card stack" onSubmit={submit} noValidate aria-labelledby="signin-title">
        <div>
          <p className="brand brand--static">
            <span className="brand__mark" aria-hidden="true">BT</span>
            <span>{SHOP_NAME}</span>
          </p>
          <h1 id="signin-title">Staff sign-in</h1>
          <p className="muted">Paste the shop's staff token. It is stored in this browser until you sign out.</p>
        </div>
        {notice && <Banner tone={isError ? 'error' : 'info'}>{notice}</Banner>}
        <TextField
          id="staff-token"
          label="Staff token"
          type="password"
          required
          autoComplete="current-password"
          autoFocus
          value={token}
          onChange={(e) => setTokenInput(e.target.value)}
        />
        <button type="submit" className="button button--block" disabled={checking}>
          {checking ? 'Checking…' : 'Sign in'}
        </button>
        <p className="muted small">
          Customer? <Link to="/track">Track your repair</Link>
        </p>
      </form>
    </main>
  );
}
