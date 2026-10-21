import type { ReactNode } from 'react';
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router';

import { SHOP_NAME } from '../config';
import { clearToken, getToken } from '../lib/tokenStore';

const NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/tickets', label: 'Tickets', end: true },
  { to: '/customers', label: 'Customers' },
  { to: '/tickets/new', label: 'New ticket' },
];

/** Guard + chrome for staff pages: no token → sign-in. */
export function RequireToken({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!getToken()) return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

export function StaffLayout() {
  const navigate = useNavigate();

  function signOut() {
    clearToken();
    navigate('/sign-in', { replace: true, state: { message: 'You have been signed out.' } });
  }

  return (
    <RequireToken>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar__inner">
          <NavLink to="/dashboard" className="brand">
            <span className="brand__mark" aria-hidden="true">BT</span>
            <span>{SHOP_NAME}</span>
          </NavLink>
          <nav aria-label="Main" className="nav">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className="nav__link">
                {item.label}
              </NavLink>
            ))}
          </nav>
          <button type="button" className="button button--ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <main id="main" className="container" tabIndex={-1}>
        <Outlet />
      </main>
    </RequireToken>
  );
}
