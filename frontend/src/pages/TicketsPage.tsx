import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';

import { api } from '../api/client';
import { TICKET_STATUSES, type TicketStatus } from '../api/types';
import { TicketTable } from '../components/TicketTable';
import { EmptyState, ErrorBanner, Loading, PageHeader, Pagination } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { statusLabel } from '../lib/statuses';

export const TICKETS_PAGE_SIZE = 20;

function readStatus(value: string | null): TicketStatus | undefined {
  return (TICKET_STATUSES as readonly string[]).includes(value ?? '') ? (value as TicketStatus) : undefined;
}

export function TicketsPage() {
  const [params, setParams] = useSearchParams();
  const status = readStatus(params.get('status'));
  const q = params.get('q') ?? '';
  const offset = Math.max(0, Number.parseInt(params.get('offset') ?? '0', 10) || 0);
  const [search, setSearch] = useState(q);

  const { data, error, loading } = useApi(
    () => api.listTickets({ status, q: q || undefined, limit: TICKETS_PAGE_SIZE, offset }),
    `${status}|${q}|${offset}`,
  );

  function update(next: { status?: string; q?: string; offset?: number }) {
    const merged = { status: status ?? '', q, offset: 0, ...next };
    const nextParams = new URLSearchParams();
    if (merged.status) nextParams.set('status', merged.status);
    if (merged.q) nextParams.set('q', merged.q);
    if (merged.offset) nextParams.set('offset', String(merged.offset));
    setParams(nextParams);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    update({ q: search.trim() });
  }

  const filtered = Boolean(status || q);

  return (
    <>
      <PageHeader
        title="Tickets"
        actions={
          <Link to="/tickets/new" className="button">
            New ticket
          </Link>
        }
      />
      <div className="toolbar">
        <form className="toolbar__search" role="search" onSubmit={submitSearch}>
          <label htmlFor="ticket-search" className="sr-only">
            Search tickets
          </label>
          <input
            id="ticket-search"
            type="search"
            maxLength={100}
            placeholder="Code, customer, brand or model"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button type="submit" className="button button--secondary">
            Search
          </button>
        </form>
        <div className="toolbar__filter">
          <label htmlFor="status-filter">Status</label>
          <select id="status-filter" value={status ?? ''} onChange={(e) => update({ status: e.target.value })}>
            <option value="">All statuses</option>
            {TICKET_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <ErrorBanner error={error} title="Could not load tickets" />
      {loading && <Loading />}
      {!loading && data && data.items.length === 0 && (
        <EmptyState>
          {filtered ? (
            <>
              No tickets match these filters.{' '}
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setSearch('');
                  setParams(new URLSearchParams());
                }}
              >
                Clear filters
              </button>
            </>
          ) : (
            <>
              No tickets yet. <Link to="/tickets/new">Create the first one</Link>.
            </>
          )}
        </EmptyState>
      )}
      {!loading && data && data.items.length > 0 && (
        <>
          <p className="muted small" aria-live="polite">
            {data.total} ticket{data.total === 1 ? '' : 's'}
          </p>
          <TicketTable tickets={data.items} caption="Tickets" />
          <Pagination
            total={data.total}
            limit={TICKETS_PAGE_SIZE}
            offset={offset}
            onChange={(next) => update({ offset: next })}
          />
        </>
      )}
    </>
  );
}
