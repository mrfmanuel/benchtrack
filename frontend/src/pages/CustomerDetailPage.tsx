import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { api } from '../api/client';
import { CustomerForm } from '../components/CustomerForm';
import { TicketTable } from '../components/TicketTable';
import { Banner, EmptyState, ErrorBanner, Loading, PageHeader, Pagination } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { formatDate } from '../lib/format';
import { NotFoundPage } from './NotFoundPage';

const PAGE_SIZE = 20;

export function CustomerDetailPage() {
  const customerId = Number(useParams().id);
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const [offset, setOffset] = useState(0);
  const customer = useApi(() => api.getCustomer(customerId), `customer-${customerId}`);
  const tickets = useApi(
    () => api.listTickets({ customer_id: customerId, limit: PAGE_SIZE, offset }),
    `customer-tickets-${customerId}-${offset}`,
  );

  if (!Number.isInteger(customerId) || customerId < 1 || customer.error?.status === 404) {
    return <NotFoundPage what="Customer" />;
  }
  if (customer.error) return <ErrorBanner error={customer.error} title="Could not load the customer" />;
  if (!customer.data) return <Loading />;
  const c = customer.data;

  return (
    <>
      <PageHeader
        title={c.name}
        actions={
          <Link to={`/tickets/new?customer_id=${c.id}`} className="button">
            New ticket for this customer
          </Link>
        }
      >
        <p className="muted">Customer since {formatDate(c.created_at)}</p>
      </PageHeader>

      <section className="card section" aria-labelledby="contact-title">
        {saved && !editing && <Banner tone="success">Customer saved.</Banner>}
        {editing ? (
          <>
            <h2 id="contact-title">Edit customer</h2>
            <CustomerForm
              customer={c}
              onSaved={(updated) => {
                customer.setData(updated);
                setEditing(false);
                setSaved(true);
                tickets.reload(); // ticket rows embed the customer's name and phone
              }}
              onCancel={() => setEditing(false)}
            />
          </>
        ) : (
          <>
            <div className="card__header">
              <h2 id="contact-title">Contact</h2>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => {
                  setSaved(false);
                  setEditing(true);
                }}
              >
                Edit
              </button>
            </div>
            <dl className="details">
              <dt>Phone</dt>
              <dd>{c.phone}</dd>
              <dt>Email</dt>
              <dd>{c.email ?? '—'}</dd>
            </dl>
          </>
        )}
      </section>

      <section className="section" aria-labelledby="customer-tickets-title">
        <h2 id="customer-tickets-title">Tickets</h2>
        <ErrorBanner error={tickets.error} title="Could not load tickets" />
        {tickets.loading && !tickets.data && <Loading />}
        {tickets.data && tickets.data.items.length === 0 && <EmptyState>No tickets for this customer yet.</EmptyState>}
        {tickets.data && tickets.data.items.length > 0 && (
          <>
            <TicketTable tickets={tickets.data.items} hideCustomer caption={`Tickets of ${c.name}`} />
            <Pagination total={tickets.data.total} limit={PAGE_SIZE} offset={offset} onChange={setOffset} />
          </>
        )}
      </section>
    </>
  );
}
