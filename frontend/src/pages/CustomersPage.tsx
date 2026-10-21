import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';

import { api } from '../api/client';
import { CustomerForm } from '../components/CustomerForm';
import { EmptyState, ErrorBanner, Loading, PageHeader, Pagination } from '../components/ui';
import { useApi } from '../hooks/useApi';
import { formatDate } from '../lib/format';

const PAGE_SIZE = 20;

export function CustomersPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const offset = Math.max(0, Number.parseInt(params.get('offset') ?? '0', 10) || 0);
  const [search, setSearch] = useState(q);
  const [creating, setCreating] = useState(false);

  const { data, error, loading } = useApi(
    () => api.listCustomers({ q: q || undefined, limit: PAGE_SIZE, offset }),
    `${q}|${offset}`,
  );

  function go(nextQ: string, nextOffset: number) {
    const next = new URLSearchParams();
    if (nextQ) next.set('q', nextQ);
    if (nextOffset) next.set('offset', String(nextOffset));
    setParams(next);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    go(search.trim(), 0);
  }

  return (
    <>
      <PageHeader
        title="Customers"
        actions={
          !creating && (
            <button type="button" className="button" onClick={() => setCreating(true)}>
              New customer
            </button>
          )
        }
      />

      {creating && (
        <section className="card section" aria-labelledby="new-customer-title">
          <h2 id="new-customer-title">New customer</h2>
          <CustomerForm
            onSaved={(customer) => navigate(`/customers/${customer.id}`)}
            onCancel={() => setCreating(false)}
          />
        </section>
      )}

      <form className="toolbar toolbar__search" role="search" onSubmit={submitSearch}>
        <label htmlFor="customer-search" className="sr-only">
          Search customers
        </label>
        <input
          id="customer-search"
          type="search"
          maxLength={100}
          placeholder="Name or phone"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="button button--secondary">
          Search
        </button>
      </form>

      <ErrorBanner error={error} title="Could not load customers" />
      {loading && <Loading />}
      {!loading && data && data.items.length === 0 && (
        <EmptyState>{q ? `No customers match “${q}”.` : 'No customers yet. Add the first one above.'}</EmptyState>
      )}
      {!loading && data && data.items.length > 0 && (
        <>
          <div className="table-wrap">
            <table className="table table--responsive">
              <caption className="sr-only">Customers</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Phone</th>
                  <th scope="col">Email</th>
                  <th scope="col">Since</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((customer) => (
                  <tr key={customer.id}>
                    <td data-label="Name">
                      <Link to={`/customers/${customer.id}`}>{customer.name}</Link>
                    </td>
                    <td data-label="Phone">{customer.phone}</td>
                    <td data-label="Email">{customer.email ?? '—'}</td>
                    <td data-label="Since">{formatDate(customer.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination total={data.total} limit={PAGE_SIZE} offset={offset} onChange={(next) => go(q, next)} />
        </>
      )}
    </>
  );
}
