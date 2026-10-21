import { useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router';

import { api, type ApiError } from '../api/client';
import type { Customer, CustomerSummary } from '../api/types';
import { CustomerForm } from '../components/CustomerForm';
import { TicketFields } from '../components/TicketFields';
import { EmptyState, ErrorBanner, Loading, PageHeader } from '../components/ui';
import { toApiError, useApi } from '../hooks/useApi';
import { splitFieldErrors, type FieldErrors } from '../lib/forms';
import { EMPTY_TICKET_FORM, TICKET_FORM_FIELDS, formValuesToPayload, type TicketFormValues } from '../lib/ticketForm';

export function NewTicketPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const presetId = Number.parseInt(params.get('customer_id') ?? '', 10);
  const preset = useApi(
    () => (presetId > 0 ? api.getCustomer(presetId) : Promise.resolve(null)),
    `preset-${presetId}`,
  );

  const [picked, setPicked] = useState<CustomerSummary | null>(null);
  const customer = picked ?? preset.data;

  const [values, setValues] = useState<TicketFormValues>(EMPTY_TICKET_FORM);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [customerError, setCustomerError] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setCustomerError(null);
    if (!customer) {
      setCustomerError('Choose or create a customer first.');
      return;
    }
    const result = formValuesToPayload(values);
    if ('errors' in result) {
      setFieldErrors(result.errors);
      return;
    }
    setSaving(true);
    try {
      const ticket = await api.createTicket({ customer_id: customer.id, ...result.payload });
      navigate(`/tickets/${ticket.id}`);
    } catch (err) {
      const apiError = toApiError(err);
      const { fields, other } = splitFieldErrors(apiError.fieldErrors, [...TICKET_FORM_FIELDS, 'customer_id']);
      setCustomerError(fields.customer_id ?? null);
      setFieldErrors(fields);
      setError(other.length || !apiError.fieldErrors.length ? apiError : null);
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader title="New ticket" />
      <section className="card section" aria-labelledby="customer-step">
        <h2 id="customer-step">1. Customer</h2>
        {!picked && <ErrorBanner error={preset.error} title="Could not load the selected customer" />}
        {preset.loading && presetId > 0 ? (
          <Loading label="Loading customer…" />
        ) : customer ? (
          <div className="picked">
            <p>
              <strong>{customer.name}</strong> · {customer.phone}
            </p>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                setPicked(null);
                preset.setData(null);
              }}
            >
              Change customer
            </button>
          </div>
        ) : (
          <CustomerPicker onPick={setPicked} />
        )}
        {customerError && (
          <p className="field__error" role="alert">
            {customerError}
          </p>
        )}
      </section>

      <form className="card section stack" onSubmit={submit} noValidate aria-labelledby="device-step">
        <h2 id="device-step">2. Device and issue</h2>
        <ErrorBanner error={error} title="Ticket not created" />
        <TicketFields values={values} errors={fieldErrors} onChange={setValues} />
        <div className="actions">
          <button type="submit" className="button" disabled={saving}>
            {saving ? 'Creating…' : 'Create ticket'}
          </button>
        </div>
      </form>
    </>
  );
}

function CustomerPicker({ onPick }: { onPick: (customer: Customer) => void }) {
  const [mode, setMode] = useState<'search' | 'create'>('search');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const results = useApi(
    () => (query ? api.listCustomers({ q: query, limit: 10 }) : Promise.resolve(null)),
    `pick-${query}`,
  );

  if (mode === 'create') {
    return (
      <CustomerForm
        idPrefix="new-customer"
        submitLabel="Create customer and continue"
        onSaved={onPick}
        onCancel={() => setMode('search')}
      />
    );
  }

  return (
    <div className="stack">
      <form
        className="toolbar__search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search.trim());
        }}
      >
        <label htmlFor="pick-customer" className="sr-only">
          Find a customer by name or phone
        </label>
        <input
          id="pick-customer"
          type="search"
          maxLength={100}
          placeholder="Find by name or phone"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="submit" className="button button--secondary">
          Find
        </button>
        <button type="button" className="button button--ghost" onClick={() => setMode('create')}>
          New customer
        </button>
      </form>
      <ErrorBanner error={results.error} title="Search failed" />
      {query && results.loading && <Loading label="Searching…" />}
      {results.data && results.data.items.length === 0 && (
        <EmptyState>
          No customers match “{query}”.{' '}
          <button type="button" className="link-button" onClick={() => setMode('create')}>
            Create a new customer
          </button>
        </EmptyState>
      )}
      {results.data && results.data.items.length > 0 && (
        <ul className="pick-list" aria-label="Matching customers">
          {results.data.items.map((c) => (
            <li key={c.id}>
              <button type="button" className="pick-list__item" onClick={() => onPick(c)}>
                <strong>{c.name}</strong>
                <span className="muted">{c.phone}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
