import { Link } from 'react-router';

import { TICKET_STATUSES } from '../api/types';
import { api } from '../api/client';
import { TicketTable } from '../components/TicketTable';
import { EmptyState, ErrorBanner, Loading, PageHeader } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { STATUS_TONES, statusLabel } from '../lib/statuses';

export function DashboardPage() {
  const { data, error, loading, reload } = useApi(() => api.getDashboard(), 'dashboard');

  return (
    <>
      <PageHeader
        title="Dashboard"
        actions={
          <Link to="/tickets/new" className="button">
            New ticket
          </Link>
        }
      />
      <ErrorBanner error={error} title="Could not load the dashboard">
        <button type="button" className="button button--secondary" onClick={reload}>
          Try again
        </button>
      </ErrorBanner>
      {loading && !data && <Loading />}
      {data && (
        <>
          <section aria-labelledby="counts-title">
            <h2 id="counts-title" className="sr-only">
              Tickets per status
            </h2>
            <ul className="status-cards">
              {TICKET_STATUSES.map((status) => (
                <li key={status}>
                  <Link to={`/tickets?status=${status}`} className={`status-card status-card--${STATUS_TONES[status]}`}>
                    <span className="status-card__count">{data.counts[status]}</span>
                    <span className="status-card__label">{statusLabel(status)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
          <section className="section" aria-labelledby="stale-title">
            <h2 id="stale-title">Stale tickets</h2>
            <p className="muted">Open tickets not updated for more than 7 days.</p>
            {data.stale_tickets.length === 0 ? (
              <EmptyState>Nothing is stale. Every open ticket was touched in the last 7 days.</EmptyState>
            ) : (
              <TicketTable tickets={data.stale_tickets} showIdle caption="Stale tickets" />
            )}
          </section>
        </>
      )}
    </>
  );
}
