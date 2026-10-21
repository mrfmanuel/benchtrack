import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';

import { api, type ApiError } from '../api/client';
import type { Customer, CustomerCreate } from '../api/types';
import { toApiError } from '../hooks/useApi';
import { existingCustomerId } from '../lib/errors';
import { blankToNull, changedFields, splitFieldErrors } from '../lib/forms';
import { TextField } from './fields';
import { Banner, ErrorBanner } from './ui';

const FIELDS = ['name', 'phone', 'email'] as const;

interface Props {
  /** Edit this customer; create a new one when omitted. */
  customer?: Customer;
  onSaved: (customer: Customer) => void;
  onCancel?: () => void;
  submitLabel?: string;
  /** Prefix for input ids, so two forms can live on one page. */
  idPrefix?: string;
}

export function CustomerForm({ customer, onSaved, onCancel, submitLabel, idPrefix = 'customer' }: Props) {
  const [name, setName] = useState(customer?.name ?? '');
  const [phone, setPhone] = useState(customer?.phone ?? '');
  const [email, setEmail] = useState(customer?.email ?? '');
  const [error, setError] = useState<ApiError | null>(null);
  const [saving, setSaving] = useState(false);
  const [unchanged, setUnchanged] = useState(false);

  const { fields, other } = splitFieldErrors(error?.fieldErrors ?? [], FIELDS);
  const duplicateId = error ? existingCustomerId(error) : null;
  if (duplicateId !== null) fields.phone = error!.message;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setUnchanged(false);
    const payload: CustomerCreate = { name: name.trim(), phone: phone.trim(), email: blankToNull(email) };
    let changes: Partial<CustomerCreate> = payload;
    if (customer) {
      changes = changedFields(customer, payload);
      if (Object.keys(changes).length === 0) {
        setUnchanged(true);
        return;
      }
    }
    setSaving(true);
    try {
      const saved = customer
        ? await api.updateCustomer(customer.id, changes)
        : await api.createCustomer(payload);
      onSaved(saved);
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setSaving(false);
    }
  }

  const id = (field: string) => `${idPrefix}-${field}`;

  return (
    <form className="stack" onSubmit={submit} noValidate aria-label={customer ? 'Edit customer' : 'New customer'}>
      {duplicateId !== null ? (
        <Banner tone="error" title="Duplicate phone number">
          <p>
            {error!.message}{' '}
            {duplicateId !== customer?.id && <Link to={`/customers/${duplicateId}`}>Open that customer</Link>}
          </p>
        </Banner>
      ) : (
        <ErrorBanner error={error} title="Customer not saved">
          {other.length > 0 && (
            <ul>
              {other.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          )}
        </ErrorBanner>
      )}
      {unchanged && <Banner tone="info">Nothing to save — no field was changed.</Banner>}
      <div className="grid-2">
        <TextField
          id={id('name')}
          label="Name"
          required
          maxLength={100}
          autoComplete="off"
          value={name}
          error={fields.name}
          onChange={(e) => setName(e.target.value)}
        />
        <TextField
          id={id('phone')}
          label="Phone"
          required
          type="tel"
          maxLength={20}
          autoComplete="off"
          hint="8–15 digits, optional leading +. Spaces and dashes are fine."
          value={phone}
          error={fields.phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        <TextField
          id={id('email')}
          label="Email"
          type="email"
          maxLength={254}
          autoComplete="off"
          value={email}
          error={fields.email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <div className="actions">
        <button type="submit" className="button" disabled={saving}>
          {saving ? 'Saving…' : (submitLabel ?? (customer ? 'Save changes' : 'Create customer'))}
        </button>
        {onCancel && (
          <button type="button" className="button button--secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
