import { Link, Outlet } from 'react-router';

import { SHOP_NAME } from '../config';

/** Minimal customer-facing chrome: no staff navigation, no token. */
export function PublicLayout() {
  return (
    <div className="public">
      <header className="public__header">
        <Link to="/track" className="brand">
          <span className="brand__mark" aria-hidden="true">BT</span>
          <span>{SHOP_NAME}</span>
        </Link>
      </header>
      <main id="main" className="public__main">
        <Outlet />
      </main>
      <footer className="public__footer">Repair tracking by BenchTrack</footer>
    </div>
  );
}
